# -*- coding: utf-8 -*-

import ast
import datetime
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import date_utils
from ..tools.utils import is_callable_method, convert_from_external_data, insert_data_sql, safe_call_method

import json
import traceback
import logging

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
        [('draft', 'Draft'), ('process', 'Process'), ('need_resolve', 'Need Resolve'), ('error', 'Error'),
         ('done', 'Done'), ]
    )
    name = fields.Char()
    display_name = fields.Char()
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy'
    )
    external_model = fields.Char()
    external_app_name = fields.Char()
    internal_model = fields.Char()

    external_odoo_id = fields.Integer()
    external_last_update = fields.Datetime()
    external_deleted = fields.Boolean(
        help="""
        Flag bahwa di external data sudah di delete
        """
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
        return self.sync_strategy_id or self.env['external.data.sync.strategy'].search(
            [('external_app_name', '=', self.external_app_name),
             ('external_model', '=', self.external_model),
             ('internal_model', '=', self.internal_model)], limit=1)

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
        with self.env.cr.savepoint():
            json_data = self.get_external_one_data()
            self.write({
                'need_get_data_json': False,
                'data_json': json.dumps(json_data)
            })
        return json_data

    def action_reset_related(self):
        for rec in self:
            rec.related_ids = False
        # [(5)]

    def is_relation_field_ignore(self):
        return self.get_sync_strategy().relation_field_ignore

    def is_all_related_done(self):
        for r in self.related_ids:
            if not r.mandatory_before_create:
                continue
            if r.state != 'done':
                return False
        return True

    def get_related_data(self, field, value):

        related = self.related_ids.filtered(lambda r: r.name == field.name)
        if related:
            related.data_json = json.dumps(value)
        elif self.sync_strategy_id and value:
            parent_sync_strategy = self.sync_strategy_id
            sync_strategy = self.sync_strategy_id.lookup_strategy(
                field.comodel_name, parent_sync_strategy=parent_sync_strategy,
                external_app_name=parent_sync_strategy.external_app_name
            )

            if sync_strategy and field.type == 'one2many' and isinstance(value, list) and isinstance(value[0], dict):
                self.related_ids.create({
                    'external_data_sync_id': self.id,
                    'sync_strategy_id': sync_strategy.id,
                    'name': field.name,
                    'internal_model': field.comodel_name,
                    'inverse_field': field.inverse_name if field.type == 'one2many' else None,
                    'field_type': field.type,
                    'state': 'draft',
                    'data_json': json.dumps(value)
                })
            elif field.type == 'many2one':
                self.related_ids.create({
                    'external_data_sync_id': self.id,
                    'sync_strategy_id': int(sync_strategy) or None,
                    'name': field.name,
                    'internal_model': field.comodel_name,
                    'field_type': field.type,
                    'state': 'draft',
                    'data_json': json.dumps(value)
                })
            return None
        return related.get_data_relation()

    def data_from_external(self, item, sync_strategy):
        if not sync_strategy:
            raise UserError("Sync Strategy Not found")
        external_odoo_id = item.get('id')
        external_last_update = item.get('write_date')
        display_name = item.get('display_name')

        if isinstance(external_last_update, str):
            external_last_update = fields.Datetime.to_datetime(external_last_update)

        input_dict = {
            'display_name': display_name or f'ID {external_odoo_id}',
            'external_last_update': external_last_update,
            'data_json': json.dumps([external_odoo_id, display_name])
        }
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('sync_strategy_id', '=', sync_strategy.id)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            if existing.external_last_update >= external_last_update and existing.internal_odoo_id:
                _logger.info("Data tidak perlu di update karena data lebih baru atau sama.")
                return existing

            if existing.state != 'process' and existing.is_update_able_from_external():
                input_dict['state'] = 'process'
                existing.write(input_dict)
            else:
                return existing
        else:
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
                input_dict = {'state': 'process'}
                existing.write(input_dict)
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

    def prepare_input_external(self, item, **kwargs):
        parent_object = self
        input_dict = self.sync_strategy_id.prepare_input_external(parent_object, item, **kwargs)
        input_dict.update(self.related_ids.get_All_data_relation() or {})
        return input_dict

    def force_update_from_external(self):
        self.need_get_data_json = True
        self.request_datetime = fields.Datetime.now()
        if self.state == 'done':
            self.state='process'

    def is_update_able_from_external(self):
        return self.sync_strategy_id.is_update_able_from_external()

    def is_update_only_from_external(self):
        return self.sync_strategy_id.is_update_only_from_external()

    def is_create_able_from_external(self):
        return self.sync_strategy_id.is_create_able_from_external()

    def write_done_internal_odoo(self, internal_odoo, payload=None):
        if internal_odoo:
            done_data = {
                'internal_odoo_id': internal_odoo.id,
                'state': 'done',
                'last_success': fields.Datetime.now(),
                'last_processing_datetime': fields.Datetime.now()
            }
            if payload:
                done_data['payload_json'] = json.dumps(payload, default=date_utils.json_default)

            self.write(done_data)

        return internal_odoo

    def ensure_have_sync_strategy(self):
        sync_strategy = self.get_sync_strategy()
        if not self.sync_strategy_id != sync_strategy:
            self.sync_strategy_id = sync_strategy
        return sync_strategy


    def process_data(self):
        try:
            item = self.get_json_data_for_create()
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

            ModelObject = sync_strategy.internal_model_object()
            existing = self.get_internal_object(ModelObject)
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

            if is_callable_method(ModelObject, sync_strategy.internal_process_method):
                method = getattr(ModelObject, sync_strategy.internal_process_method)
                existing = method(item, sync_strategy=sync_strategy, data_sync=self)
                self.write_done_internal_odoo(existing)
            else:
                with self.env.cr.savepoint():
                    input_dict = self.prepare_input_external(item)
                payload = {}
                self.flush()
                with self.env.cr.savepoint():
                    if self.is_all_related_done():
                        if sync_strategy.internal_id_same_as_external and not existing:
                            existing = sync_strategy.internal_lookup(item)
                        if existing and self.is_update_able_from_external():
                            _logger.info(f"Update {self.internal_model} with external id {self.internal_odoo_id}")
                            existing.write(input_dict)
                            payload.update(input_dict)
                        if not existing and self.is_create_able_from_external():
                            _logger.info(f"Create {self.internal_model}")
                            internal_context = self.get_internal_context()
                            if sync_strategy.internal_id_same_as_external:
                                internal_odoo_id = sync_strategy.get_internal_id_same_as_external(item)
                                input_dict['id'] = internal_odoo_id
                                existing = insert_data_sql(ModelObject.with_context(internal_context), [input_dict])[0]
                            else:
                                existing = ModelObject.with_context(internal_context).create([input_dict])[0]
                            payload.update(input_dict)
                        if existing:
                            after_data = self.process_field_after_create(existing) or {}
                            if after_data:
                                payload.update(after_data)
                            self.write_done_internal_odoo(existing, payload)
                        else:
                            _logger.info(f"No update or Create {item.get('id')}")
                            self.write({
                                'error_info': "Cannot update and create",
                                'state': 'need_resolve',
                                'last_processing_datetime': fields.Datetime.now(),
                                'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=24),
                            })
                    else:
                        _logger.info("Delay proses data karena masih ada related data yang belum selesai. (%s) [%s] %s"
                                 , self.internal_model, self.external_model, self.external_odoo_id)


                if is_callable_method(existing, 'external_data_sync_done'):
                    with self.env.cr.savepoint():
                        safe_call_method(existing, 'external_data_sync_done', kwargs={
                            'data_external': item,
                            'data_update': input_dict,
                            'external_model': self.external_model,
                            'external_app_name': self.external_app_name,
                            'external_odoo_id': self.external_odoo_id,
                        })

        except Exception as ex:
            self.write_error(traceback.format_exc())
        finally:
            if self.is_all_related_done() and self.state == 'process':
                self.state = 'need_resolve'

    def write_error(self, stack_trace):
        self.write({
            'error_info': stack_trace,
            'state': 'error',
            'last_error': fields.Datetime.now(),
            'last_processing_datetime': fields.Datetime.now(),
            'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        })

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

    def cron_process_data(self, limit=1000):
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        to_process = self.search(
            [('need_get_data_json', '=', True)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for t in to_process:
            try:
                t.process_data()
            except Exception:
                self.env.cr.rollback()
                _logger.exception("error")
                t.write({
                    'error_info': traceback.format_exc(),
                    'state': 'error',
                    'last_error': fields.Datetime.now(),
                    'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                })
            self.env.cr.commit()
            if fields.Datetime.now() > limit_time:
                break

        to_process = self.search(
            [('state', '!=', 'done'),
             '|',
             ('next_processing_datetime', '<=', fields.Datetime.now()),
             ('next_processing_datetime', '=', False)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for t in to_process:
            try:
                t.process_data()
            except Exception:
                self.env.cr.rollback()
                _logger.exception("error")
                t.write({
                    'error_info': traceback.format_exc(),
                    'state': 'error',
                    'last_error': fields.Datetime.now(),
                    'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                })
            self.env.cr.commit()
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

        for t in sync_related:
            try:
                t.process_data()
                if t.state == 'done' and t.external_data_sync_id:
                    external_data_sync |= t.external_data_sync_id
                else:
                    t.write({
                        'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                    })
            except Exception:
                self.env.cr.rollback()
                t.write({
                    'error_info': traceback.format_exc(),
                    'state': 'error',
                    'last_error': fields.Datetime.now(),
                    'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                })
                continue
            if fields.Datetime.now() > limit_time:
                break
            self.env.cr.commit()
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        for t in external_data_sync:
            try:
                t.process_data()
            except Exception:
                self.env.cr.rollback()
                continue
            self.env.cr.commit()
            if fields.Datetime.now() > limit_time:
                break

        return True

    def get_internal_context(self):
        return self.sync_strategy_id.get_internal_context()

    def get_internal_object(self,model=None):
        if not model and self.sync_strategy_id:
            model = self.sync_strategy_id.internal_model_object()
        if not model and self.internal_model:
            model = self.env[self.internal_model]
        if model:
            return model.browse(self.internal_odoo_id)
        return model

    def process_field_after_create(self, existing):
        after_create = {}
        need_resolve = False
        for r in self.related_ids:
            if r.field_after_create or r.state!='done':
                r.process_field_after_create()
            if r.field_type == 'many2one':
                data_relation = r.get_data_relation()
                if data_relation:
                    after_create[r.name] = data_relation
            if r.state!='done':
                need_resolve = True

        if after_create and existing:
            existing.write(after_create)

        if need_resolve:
            self.write({
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

    def get_sync_strategy(self):
        return self.sync_strategy_id.ensure_internal_context()

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
        # digunakan untuk mengirim data ke server external
        if not internal:
            return [0]

        if not isinstance(internal, models.BaseModel):
            _logger.error("Internal Object must")
            if raise_not_found_exception:
                raise ValueError("Internal Object must")
            return [0]

        if sync_strategy:
            return sync_strategy.reverse_mapping(internal, raise_not_found_exception=raise_not_found_exception)

        if not external_app_name:
            _logger.error("external_app_name not set")
            if raise_not_found_exception:
                raise ValueError("external_app_name not set")
            return [0]

        if not external_model:
            _logger.error("external_model not set")
            if raise_not_found_exception:
                raise ValueError("external_model not set")
            return [0]

        domain = [('internal_odoo_id', 'in', internal.ids), ('external_app_name', '=', external_app_name),
                  ('external_model', '=', external_model), ('internal_model', '=', internal._name)]

        rows = self.search_read(
            domain,
            fields=['internal_odoo_id', 'external_odoo_id']
        )

        mapping = defaultdict(list)
        for r in rows:
            mapping[r['internal_odoo_id']].append(r['external_odoo_id'])

        result_map = dict(mapping)

        not_mapped_ids = set(internal.ids) - result_map.keys()
        if not_mapped_ids:
            _logger.error("found not mapped data")
            if raise_not_found_exception:
                raise ValueError("found not mapped data [%s]" % str(not_mapped_ids))

        return result_map

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
        input_dict = self.prepare_input_external(item)
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
                'sync_strategy_id':sync_strategy.id,
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