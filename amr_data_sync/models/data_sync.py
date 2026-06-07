# -*- coding: utf-8 -*-

import datetime
import json
import logging
import traceback
from collections import defaultdict

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.addons.amr_jsonrpc.utils import savepoint
from odoo.exceptions import UserError
from odoo.tools import date_utils

from ..tools.utils import convert_from_external_data, insert_data_sql

_logger = logging.getLogger(__name__)


class ExternalDataSync(models.Model):
    _name = 'external.data.sync'
    _description = """
    Model untuk menyimpan infomasi terkait object yang berasala dari aplikasi external.
    
    Model ini juga bisa di jadikan mapping bila mendapatakan data dari external untuk refeensi object.
    """
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('process', 'Process'),
         ('need_resolve', 'Need Resolve'), ('error', 'Error'),
         ('done', 'Done'), ]
    )
    name = fields.Char()
    display_name = fields.Char()
    company_id = fields.Many2one('res.company')
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        ondelete='set null'
    )
    external_model = fields.Char()
    external_app_name = fields.Char()
    internal_model = fields.Char()

    external_odoo_id = fields.Integer()
    external_last_update = fields.Datetime()
    external_deleted = fields.Boolean(
        help="Flag bahwa di external data sudah di delete"
    )
    external_archived = fields.Boolean(
        help="Flag bahwa di external data sudah di archived"
    )
    internal_odoo_id = fields.Integer(
        help="""
        Ini adalah tanda bahwa external data telah di mapping ke internal data.
        """
    )

    last_success = fields.Datetime()
    last_error = fields.Datetime()

    need_get_data_json = fields.Boolean(default=True, help="Flag for get data from external")
    data_json = fields.Text()
    error_info = fields.Text()
    payload_json = fields.Text()
    next_processing_datetime = fields.Datetime(default=fields.Datetime.now)
    last_processing_datetime = fields.Datetime()
    request_datetime = fields.Datetime(default=fields.Datetime.now)
    deleted_datetime = fields.Datetime(
        help="Waktu data ini di tandai sebagai deleted dari external system."
    )
    archived_datetime = fields.Datetime(
        help="Waktu data ini di tandai sebagai archived internal system"
    )
    related_ids = fields.One2many(
        'external.data.sync.related', 'external_data_sync_id',
        string='Related Data',
        help="Related data linked to this external data sync record."
    )

    def get_external_application_name(self):
        return self.external_app_name or (self.server_sync_id and self.server_sync_id.get_application_name()) or None

    def create(self, vals_list):
        for vals in vals_list:
            if 'sync_strategy_id' in vals and vals['sync_strategy_id']:
                strategy = self.env['external.data.sync.strategy'].browse(vals['sync_strategy_id'])
                if not strategy:
                    raise UserError(_("Strategy dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
                vals['external_model'] = strategy.external_model
                vals['external_app_name'] = strategy.get_external_application_name()
                vals['internal_model'] = strategy.internal_model or strategy.external_model

            if 'state' not in vals or not vals['state']:
                vals['state'] = 'draft'
            if 'name' not in vals or not vals['name']:
                vals['name'] = vals.get('display_name') or f'ID {vals.get("external_odoo_id")}'
        return super(ExternalDataSync, self).create(vals_list)

    def write(self, vals):
        if 'sync_strategy_id' in vals and vals['sync_strategy_id']:
            strategy = self.env['external.data.sync.strategy'].browse(vals['sync_strategy_id'])
            if not strategy:
                raise UserError(_("Strategy dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
            vals['external_model'] = strategy.external_model
            vals['external_app_name'] = strategy.external_app_name
            vals['internal_model'] = strategy.internal_model or strategy.external_model

        return super(ExternalDataSync, self).write(vals)

    def get_server_sync(self):
        return self.sync_strategy_id.get_server_sync() or self.env['external.server.sync'].sudo().search(
            [('name', '=', self.external_app_name)], limit=1)

    def get_sync_strategy(self):
        sync_strategy_id = self.sync_strategy_id or self.env['external.data.sync.strategy'].search(
            [('external_app_name', '=', self.external_app_name),
             ('external_model', '=', self.external_model),
             ('internal_model', '=', self.internal_model)], limit=1)
        return sync_strategy_id.ensure_internal_context()

    def get_external_one_data(self):
        sync_strategy = self.get_sync_strategy()
        if not sync_strategy:
            raise UserError(_("Strategy Sync dengan nama %s tidak ditemukan") % self.get_external_application_name())

        return sync_strategy.get_external_one_data(self.external_odoo_id)

    def get_json_data_for_create(self):
        if not self.need_get_data_json:
            json_date = json.loads(self.data_json)
            if isinstance(json_date, dict):
                return json_date
            _logger.info("Data Json not dict")

        json_data = self.get_external_one_data()
        if json_data:
            with self.env.cr.savepoint():
                data = {
                    'need_get_data_json': False,
                    'data_json': json.dumps(json_data)
                }
                write_date = json_data.get('write_date')
                if write_date:
                    if isinstance(write_date, str):
                        write_date = fields.Datetime.to_datetime(write_date)
                    data['external_last_update'] = write_date
                self.write(data)
            return json_data
        else:
            self.write({
                'need_get_data_json': False,
                'data_json': json.dumps(json_data)
            })
            _logger.info("Deleter")
            return {'active' : False}


    def validate_json_data_for_delete(self):
        self.ensure_one()
        json_data = self.get_external_one_data()
        if not json_data:
            self.external_deleted=True
            self.action_archive_internal_odoo(self.get_internal_object(),{},{})
            return True

        return False

    def action_reset_related(self):
        for rec in self:
            rec.related_ids = False
        # [(5)]

    def is_relation_field_ignore(self):
        return self.get_sync_strategy().relation_field_ignore

    def is_mandatory_related_done(self):
        for r in self.related_ids:
            if r.mandatory_before_create and r.state not in ['need_resolve','done']:
                _logger.info("field mandatory [%s] , state %s ",r.name,r.state)
                return False
        return True

    def is_all_related_done(self):
        for r in self.related_ids:
            if r.state not in ['need_resolve','done']:
                _logger.info("field %s , state %s ",r.name,r.state)
                return False
        return True

    # @savepoint(rethrow=True)
    def get_related_data(self, field, value):
        related = self.related_ids.filtered(lambda r: r.name == field.name)
        if related:
            related.write({
                'data_json': json.dumps(value)
            })
        else:
            _logger.warning("field with value cannot process %s, value",field,value)
            return None
        # elif self.sync_strategy_id and value:
        #     parent_sync_strategy = self.sync_strategy_id
        #     sync_strategy = self.sync_strategy_id.lookup_strategy(
        #         field.comodel_name, parent_sync_strategy=parent_sync_strategy,
        #         external_app_name=parent_sync_strategy.external_app_name
        #     )
        #     if sync_strategy:
        #         external_data_sync_id = self
        #         related = self.env['external.data.sync.related'].create_or_get_related(
        #             external_data_sync_id, field.name, field.type, field_required=field.required,
        #             related_sync_strategy_id=sync_strategy,
        #             internal_model=field.comodel_name,
        #             inverse_field=field.inverse_name if field.type == 'one2many' else None,
        #             value=value
        #         )
        return related.get_data_relation()

    def data_from_external(self, item, sync_strategy, create_when_not_found=True,need_get_data_json=True):
        if not sync_strategy:
            raise UserError("Sync Strategy Not found")
        external_odoo_id = item.get('id')
        external_last_update = item.get('write_date')
        display_name = item.get('display_name')

        if isinstance(external_last_update, str):
            external_last_update = fields.Datetime.to_datetime(external_last_update)
        if need_get_data_json:
            data_json = json.dumps([external_odoo_id, display_name])
        else:
            data_json = json.dumps(item)

        input_dict = {
            'display_name': display_name or f'ID {external_odoo_id}',
            'data_json': data_json,
            'need_get_data_json': need_get_data_json
        }
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('sync_strategy_id', '=', sync_strategy.id)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            if external_last_update and existing.external_last_update and existing.internal_odoo_id:
                if existing.external_last_update >= external_last_update:
                    _logger.info("Data tidak perlu di update karena data lebih baru atau sama.")
                    return existing
                input_dict['external_last_update'] = external_last_update

            if existing.state != 'process' and existing.is_update_able_from_external():
                input_dict['state'] = 'process'
                existing.write(input_dict)
            else:
                return existing
        elif create_when_not_found:
            input_dict.update(
                external_odoo_id=external_odoo_id,
                sync_strategy_id=sync_strategy.id,
            )
            internal = sync_strategy.internal_lookup(item)
            if internal:
                input_dict.update(
                    internal_odoo_id=internal.id,
                    state='done',
                    last_success=fields.Datetime.now(),
                )
            existing = self.create([input_dict])[0]

        return existing

    def relation_from_external(self, item, sync_related):
        item = convert_from_external_data(item)
        external_odoo_id = int(item.get('id'))
        display_name = item.get('name') or item.get('display_name')

        parent_external_data_sync = sync_related.external_data_sync_id
        internal_model = sync_related.internal_model
        external_app_name = sync_related.external_app_name
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('external_app_name', '=', external_app_name),
            ('internal_model', '=', internal_model)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            if existing.state != 'done' and existing.is_update_able_from_external():
                # input_dict = {'state': 'process'}
                # existing.write(input_dict)
                existing.dispatch_process()
        elif sync_related.sync_strategy_id:
            input_dict = {
                'display_name': display_name or f'ID {external_odoo_id}',
                'data_json': f'[{external_odoo_id}, "{display_name}"]',
                'external_odoo_id': external_odoo_id,
                'external_model': internal_model,
                'internal_model': internal_model,
                'sync_strategy_id': sync_related.sync_strategy_id.id,
                'external_app_name': parent_external_data_sync.external_app_name
            }
            existing = self.create([input_dict])[0]

        return existing

    #@savepoint(rethrow=True)
    def prepare_input_external(self, item, **kwargs):
        parent_object = self
        sync_strategy = kwargs.get('sync_strategy') or self.sync_strategy_id
        input_dict = sync_strategy.prepare_input_external(parent_object, item, **kwargs)
        input_dict.update(self.related_ids.get_All_data_relation() or {})
        return input_dict

    def force_update_from_external(self):
        self.need_get_data_json = True
        self.request_datetime = fields.Datetime.now()
        if self.state == 'done':
            self.dispatch_process()
            # self.state = 'process'

    def is_update_able_from_external(self):
        return self.sync_strategy_id.is_update_able_from_external()

    def is_update_only_from_external(self):
        return self.sync_strategy_id.is_update_only_from_external()

    def is_create_able_from_external(self):
        return self.sync_strategy_id.is_create_able_from_external()

    def action_archive_internal_odoo(self,internal_odoo, item, input_dict):
        _logger.info("action_archive data %s %s.", self.internal_odoo_id ,internal_odoo)
        internal_odoo and internal_odoo.action_archive()
        _logger.info("Related Done Process after sync done")
        self.sync_strategy_id.event_external_archived_done(internal_odoo, item, input_dict)
        self.write_archived_internal_odoo(internal_odoo, input_dict)

    #@savepoint
    def write_done_internal_odoo(self, internal_odoo, payload=None):
        if internal_odoo:
            done_data = {
                'external_deleted':False,
                'external_archived': False,
                'internal_odoo_id': internal_odoo.id,
                'state': 'done',
                'last_success': fields.Datetime.now(),
                'last_processing_datetime': fields.Datetime.now()
            }
            if payload:
                done_data['payload_json'] = json.dumps(payload, default=date_utils.json_default)

            self.write(done_data)

        return internal_odoo

    def write_archived_internal_odoo(self, internal_odoo, payload=None):
        done_data = {
            'state': 'done',
            'external_archived': True,
            'archived_datetime': fields.Datetime.now(),
            'last_success': fields.Datetime.now(),
            'last_processing_datetime': fields.Datetime.now(),
            'payload_json':json.dumps(payload, default=date_utils.json_default)
        }
        self.write(done_data)

        return internal_odoo

    def write_need_resolve_internal_odoo(self, internal_odoo, payload=None):
        if internal_odoo:
            done_data = {
                'internal_odoo_id': internal_odoo.id,
                'state': 'need_resolve',
                'last_processing_datetime': fields.Datetime.now()
            }
            if payload:
                done_data['payload_json'] = json.dumps(payload, default=date_utils.json_default)

            self.write_error_safe(done_data)

        return internal_odoo

    def ensure_have_sync_strategy(self):
        sync_strategy = self.get_sync_strategy()
        if not self.sync_strategy_id != sync_strategy:
            self.sync_strategy_id = sync_strategy
        return sync_strategy

    # @savepoint(rethrow=True)
    def save_data(self, existing, item, input_dict):
        sync_strategy = self.sync_strategy_id
        if sync_strategy.internal_id_same_as_external and not existing:
            existing = sync_strategy.internal_lookup(item)
        if existing and self.is_update_able_from_external():
            _logger.info(f"Update {self.internal_model} with external id {self.internal_odoo_id}")
            existing.write(input_dict)
        if not existing and self.is_create_able_from_external():
            _logger.info(f"Create {self.internal_model}")
            if sync_strategy.internal_id_same_as_external:
                internal_odoo_id = sync_strategy.get_internal_id_same_as_external(item)
                input_dict['id'] = internal_odoo_id
                existing = insert_data_sql(existing, [input_dict])[0]
            else:
                existing = existing.create([input_dict])[0]

        return existing

    def process_data(self):
        input_dict = {}
        try:
            _logger.info("process_data start")
            item = self.get_json_data_for_create()
            inactive_data = item.get('active', True) == False or item.get('x_active', True) == False
            sync_strategy = self.get_sync_strategy()
            if not sync_strategy:
                self.write({
                    'error_info': "Without Strategy",
                    'state': 'need_resolve',
                    'last_error': fields.Datetime.now(),
                    'last_processing_datetime': fields.Datetime.now(),
                    'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=24),
                })
                return
            if 'company_id' in item:
                company = sync_strategy.lookup_company(item.get('company_id'))
                if company and company.id != self.company_id.id:
                    self.write({
                        'company_id': company.id
                    })
                if not company:
                    company = self.company_id
            else:
                company = self.company_id
            if company:
                sync_strategy = sync_strategy.ensure_internal_context(default_company_id=company.id)
            ModelObject = sync_strategy.internal_model_object()
            existing = self.get_internal_object(ModelObject)
            if inactive_data:
                if not existing:
                    self.write({
                        'error_info': "Not data active",
                    })
                self.action_archive_internal_odoo(existing, item, input_dict)
                sync_strategy.event_external_data_sync_done(existing, item, input_dict)
                _logger.info("Skip inactive data update %s", existing)
                return

            if not self.is_create_able_from_external() and not self.is_update_able_from_external():
                if not existing:
                    existing = sync_strategy.internal_lookup(item)
                if existing:
                    self.write_done_internal_odoo(existing)
                else:
                    self.write({
                        'error_info': "Cannot update and create",
                        'state': 'need_resolve',
                        'last_processing_datetime': fields.Datetime.now(),
                        'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=24),
                    })
                return

            input_dict = self.prepare_input_external(item, sync_strategy=sync_strategy)
            result_internal = sync_strategy.call_internal_process_method(existing, item, input_dict, self)
            skip_save = False
            if isinstance(result_internal, models.BaseModel):
                existing = result_internal
                skip_save = True
            elif isinstance(result_internal, dict):
                input_dict = result_internal

            if not skip_save:
                existing = self.save_data(existing, item, input_dict)

            if existing:
                after_data = self.process_field_after_create(existing) or {}
                if after_data:
                    input_dict.update(after_data)
                self.write_done_internal_odoo(existing, input_dict)
                all_related_done = self.is_all_related_done()
                if all_related_done:
                    _logger.info("Related Done Process after sync done")
                    sync_strategy.event_external_data_sync_done(existing, item, input_dict)
                else:
                    _logger.info("Delay proses data karena masih ada related data yang belum selesai. (%s) [%s] %s",
                                 self.internal_model, self.external_model, str(self.external_odoo_id)
                                 )
                    self.write({'state': 'need_resolve','error_info': "need_resolve"})

            else:
                _logger.info(f"No update or Create {item.get('id')}")

        except Exception:
            _logger.exception("Error process_data")
            self.write_error(traceback.format_exc(), input_dict)
            raise

    def write_error(self, stack_trace, payload=None):
        error_data = {
            'error_info': stack_trace,
            'state': 'error',
            'last_error': fields.Datetime.now(),
            'last_processing_datetime': fields.Datetime.now(),
            'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        }
        if payload:
            error_data['payload_json'] = json.dumps(payload, default=date_utils.json_default)
        self.write_error_safe(error_data)

    def write_error_safe(self,error_data,using_pool=False):

        if using_pool:
            _logger.info("write_error_safe using_pool %s .", self)
            with self.pool.cursor() as cr:
                # write kita ada exception
                env = api.Environment(cr, SUPERUSER_ID, self.env.context)
                self.with_env(env).write(error_data)
                cr.commit()
        else:
            _logger.info("write_error_safe not using_pool %s .", self)
            with self.env.cr.savepoint():
                self.write(error_data)

    def action_process_data(self):
        for rec in self:
            rec.process_data()

    def action_open_internal(self):
        self.ensure_one()
        return {
            'name': _('Internal Data'),
            'type': 'ir.actions.act_window',
            'res_model': self.internal_model,
            'res_id': self.internal_odoo_id,
            'view_mode': 'form',
        }

    def action_get_json_data_for_create(self):
        self.ensure_one()
        self.data_json = json.dumps(self.get_external_one_data())

    def dispatch_process(self,run_immediate=False):
        self.write({'state': 'process'})
        if run_immediate:
            id_= self.id
            with self.pool.cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                rec = env[self._name].browse(id_)
                try:
                    rec.process_data()
                    cr.commit()
                except Exception:
                    _logger.exception("Error rec %s", self)
                    cr.rollback()
                    rec = env[self._name].browse(id_)
                    rec.write_error_safe({
                        'error_info': traceback.format_exc(),
                        'state': 'error',
                        'last_error': fields.Datetime.now(),
                        'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                    })

    def cron_process_data(self, limit=1000):
        # def process_rec_id(id_):
        #     with self.pool.cursor() as cr:
        #         env = api.Environment(cr, self.env.uid, self.env.context)
        #         rec = env[self._name].browse(id_)
        #         try:
        #             rec.process_data()
        #             cr.commit()
        #         except Exception :
        #             _logger.exception("Error rec %s", rec_id)
        #             cr.rollback()
        #             rec = env[self._name].browse(id_)
        #             rec.write_error_safe({
        #                 'error_info': traceback.format_exc(),
        #                 'state': 'error',
        #                 'last_error': fields.Datetime.now(),
        #                 'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        #             })
        # def process_related_id(id_):
        #     with self.pool.cursor() as cr:
        #         env = api.Environment(cr, self.env.uid, self.env.context)
        #         rec = env['external.data.sync.related'].browse(id_)
        #         try:
        #             rec.process_data()
        #             if rec.state != 'done' or not rec.external_data_sync_id:
        #                 rec.write({
        #                     'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        #                 })
        #             cr.commit()
        #         except Exception :
        #             _logger.exception("Error rec %s", rec_id)
        #             cr.rollback()
        #             rec = env[self._name].browse(id_)
        #             rec.write_error_safe({
        #                 'error_info': traceback.format_exc(),
        #                 'state': 'error',
        #                 'last_error': fields.Datetime.now(),
        #                 'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        #             })
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        records  = self.search(
            [('need_get_data_json', '=', True)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for rec in records:
            rec.dispatch_process(True)
            if fields.Datetime.now() > limit_time:
                break
        records =self.search(
            [('state', '!=', 'done'),
             '|',
             ('next_processing_datetime', '<=', fields.Datetime.now()),
             ('next_processing_datetime', '=', False)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for rec in records :
            rec.dispatch_process(True)
            if fields.Datetime.now() > limit_time:
                break

        sync_related = self.env['external.data.sync.related'].search(
            [('state', '!=', 'done'),
             '|',
             ('next_processing_datetime', '<=', fields.Datetime.now()),
             ('next_processing_datetime', '=', False)],
            order='next_processing_datetime', limit=limit, )
        external_data_sync = self.browse()
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)

        for rec in sync_related:
            rec.dispatch_process(True)
            # process_related_id(t.id)
            # if t.state == 'done' and t.external_data_sync_id:
            #     external_data_sync |= t.external_data_sync_id

            if fields.Datetime.now() > limit_time:
                break
        # limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        # for t in external_data_sync:
        #     process_rec_id(t.id)
        #
        #     if fields.Datetime.now() > limit_time:
        #         break

        return True

    def get_internal_context(self):
        return self.sync_strategy_id.get_internal_context()

    def get_internal_object(self, model=None):
        if not isinstance(model, models.BaseModel) and self.sync_strategy_id:
            model = self.sync_strategy_id.internal_model_object()
        if not isinstance(model, models.BaseModel)  and self.internal_model:
            model = self.env[self.internal_model]
        if isinstance(model, models.BaseModel):
            return model.with_context(active_test=False).browse(self.internal_odoo_id)
        return model

    # @savepoint
    def process_field_after_create(self, existing):
        after_create = {}
        need_resolve = False
        for r in self.related_ids:
            if r.field_after_create or r.state != 'done':
                r.process_field_after_create()
            if r.field_type == 'many2one':
                data_relation = r.get_data_relation()
                if data_relation:
                    after_create[r.name] = data_relation
            if r.state != 'done':
                need_resolve = True

        if after_create and existing:
            existing.write(after_create)

        if need_resolve:
            self.write_error_safe({
                'error_info': "Issue Process Field After Create",
                'state': 'need_resolve',
                # 'last_error': fields.Datetime.now(),
                'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
            })
        return after_create

    def action_process_field_after_create(self):
        for rec in self.filtered(lambda r: r.state == 'done' and r.internal_odoo_id):
            existing = rec.get_internal_object()
            if existing:
                rec.process_field_after_create(existing)

    def get_last_sync_datetime(self, strategy):
        domain = [
            ('sync_strategy_id', '=', strategy.id),
            ('state', '=', 'done'),
            ('internal_odoo_id', '!=', False),
        ]
        last_sync = self.search(domain, order='last_success desc', limit=1)
        if last_sync:
            return last_sync.last_success
        return None

    # def get_sync_strategy(self):
    #     return self.sync_strategy_id.ensure_internal_context()

    def get_or_create(self, external_data, sync_strategy):
        external_data = self.ensure_external_data(external_data)
        external_odoo_id = external_data.get('id')
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('sync_strategy_id', '=', sync_strategy.id)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            return existing
        else:
            return self.data_from_external(external_data, sync_strategy)

    def reverse_mapping(
            self, internal,
            sync_strategy=None,
            external_app_name=None,
            external_model=None,
            raise_not_found_exception=True
    ):
        # return result_map(int:internal_id,list():external_id), not_mapped_ids(int:internal)
        # digunakan untuk mengirim data ke server external
        if not internal:
            return [], []

        if not isinstance(internal, models.BaseModel):
            _logger.error("Internal Object must")
            if raise_not_found_exception:
                raise ValueError("Internal Object must")
            return [], []

        if sync_strategy:
            result_map, not_mapped_ids = sync_strategy.reverse_mapping(internal, raise_not_found_exception=False)
            if not not_mapped_ids:
                return result_map, not_mapped_ids
            internal_model = sync_strategy.internal_model
            external_app_name = sync_strategy.get_external_application_name()
            external_model = sync_strategy.external_model or internal_model
        else:
            internal_model = internal._name
            result_map, not_mapped_ids = {}, set(internal.ids)

        if not external_app_name:
            _logger.error("external_app_name not set")
            if raise_not_found_exception:
                raise ValueError("external_app_name not set")
            return result_map, not_mapped_ids
        if not external_model:
            if internal_model:
                external_model = internal_model
            else:
                _logger.error("external_model not set")
                if raise_not_found_exception:
                    raise ValueError("external_model not set")
                return result_map, not_mapped_ids

        domain = [('internal_odoo_id', 'in', list(not_mapped_ids)), ('internal_model', '=', internal_model),
                  ('external_app_name', '=', external_app_name), ('external_model', '=', external_model), ]

        rows = self.search_read(
            domain,
            fields=['internal_odoo_id', 'external_odoo_id']
        )

        mapping = defaultdict(list)
        for r in rows:
            mapping[r['internal_odoo_id']].append(r['external_odoo_id'])

        result_map.update(dict(mapping))
        not_mapped_ids -= result_map.keys()

        if not not_mapped_ids:
            return result_map, not_mapped_ids

        domain = [('internal_id', 'in', list(not_mapped_ids)), ('internal_model', '=', internal_model),
                  ('external_app_name', '=', external_app_name), ('external_model', '=', external_model),
                  ('reverse_able', '=', True), ]

        rows = self.env['external.data.lookup'].search_read(
            domain,
            fields=['internal_id', 'external_id']
        )
        mapping = defaultdict(list)
        for r in rows:
            mapping[r['internal_id']].append(r['external_id'])

        result_map.update(dict(mapping))

        if not_mapped_ids:
            _logger.error("found not mapped data")
            if raise_not_found_exception:
                raise ValueError("found not mapped data [%s]" % str(not_mapped_ids))

        return result_map, not_mapped_ids

    @api.model
    def ensure_external_data(self, external_data):
        if isinstance(external_data, dict):
            return external_data
        if isinstance(external_data, list):
            if len(external_data) == 2:
                return {
                    'id': external_data[0],
                    'display_name': external_data[1]
                }
            elif external_data:
                return {
                    'id': external_data[0],
                }

        if isinstance(external_data, int):
            return {
                'id': external_data
            }
        return {}

    def action_build_payload(self):
        item = self.get_json_data_for_create()
        _logger.info("get_json_data_for_create %s ",item)
        input_dict = self.prepare_input_external(item)
        _logger.info("prepare_input_external %s ",input_dict)
        self.payload_json = json.dumps(input_dict, default=date_utils.json_default)

    def data_from_external_id(self, external_odoo_id, sync_strategy):
        if not sync_strategy:
            raise UserError("Sync Strategy Not found")
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('sync_strategy_id', '=', sync_strategy.id)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            return existing
        else:
            item = sync_strategy.get_external_one_data(external_odoo_id)
            external_last_update = item.get('write_date')
            display_name = item.get('display_name') or item.get('name')

            if isinstance(external_last_update, str):
                external_last_update = fields.Datetime.to_datetime(external_last_update)
            input_dict = {
                'display_name': display_name or f'ID {external_odoo_id}',
                'external_last_update': external_last_update,
                'sync_strategy_id': sync_strategy.id,
                'data_json': json.dumps(item),
            }
            internal = sync_strategy.internal_lookup(item)
            if internal:
                input_dict.update(
                    internal_odoo_id=internal.id,
                    state='done',
                    last_success=fields.Datetime.now(),
                )
            existing = self.create([input_dict])[0]

        return existing
