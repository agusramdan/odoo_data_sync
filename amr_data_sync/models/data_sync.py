# -*- coding: utf-8 -*-

import ast
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..tools.utils import is_callable_method

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

    data_json = fields.Text()
    error_info = fields.Text()

    next_processing_datetime = fields.Datetime()
    last_processing_datetime = fields.Datetime()

    related_ids = fields.One2many(
        'external.data.sync.related', 'external_data_sync_id',
        string='Related Data',
        help="Related data linked to this external data sync record."
    )

    def create(self, vals_list):
        for vals in vals_list:
            if 'sync_strategy_id' in vals and vals['sync_strategy_id']:
                strategy = self.env['external.data.sync.strategy'].browse(vals['sync_strategy_id'])
                if not strategy:
                    raise UserError(_("Strategy dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
                vals['external_model'] = strategy.external_model
                vals['external_app_name'] = strategy.external_app_name or strategy.server_sync_id.app_name
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
            raise UserError(_("Strategy Sync dengan nama %s tidak ditemukan") % self.external_app_name)

        return sync_strategy.get_external_one_data(self.external_odoo_id)

    def get_json_data_for_create(self):
        json_date = json.loads(self.data_json)
        if isinstance(json_date, dict):
            return json_date

        json_data = self.get_external_one_data()
        self.data_json = json.dumps(json_data)
        return json_data

    def action_reset_related(self):
        self.related_ids = False
        # [(5)]

    def is_relation_field_ignore(self):
        return self.get_sync_strategy().relation_field_ignore

    def is_all_related_done(self):
        for r in self.related_ids:
            if r.field_after_create:
                continue
            if r.state != 'done':
                return False
        return True

    def get_related_data(self, field, value):

        related = self.related_ids.filtered(lambda r: r.name == field.name)

        if related:
            related.data_json = json.dumps(value)
        elif self.sync_strategy_id:
            parent_sync_strategy = self.sync_strategy_id
            sync_strategy = self.sync_strategy_id.lookup_strategy(
                field.comodel_name, parent_sync_strategy=parent_sync_strategy,
                external_app_name=parent_sync_strategy.external_app_name)
            if sync_strategy or (
                    field.type == 'one2many' and value and isinstance(value, list) and isinstance(value[0], dict)):
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

            return None

        return related.get_data_relation()

    def data_from_external(self, item, sync_strategy):

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
            if sync_strategy:
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
        display_name = None
        # item_dict = {}
        if isinstance(item, int):
            external_odoo_id = item
        elif isinstance(item, list):
            if len(item) > 0:
                external_odoo_id = int(item[0])
            if len(item) > 1:
                display_name = item[1]
        elif isinstance(item, dict):
            # item_dict = item
            external_odoo_id = int(item.get('id'))
            display_name = item.get('name') or item.get('display_name')

        parent_external_data_sync = sync_related.external_data_sync_id
        internal_model = sync_related.internal_model
        domain = [
            ('external_odoo_id', '=', external_odoo_id),
            ('internal_model', '=', internal_model)
        ]
        existing = self.search(domain, limit=1)
        if existing:
            if existing.state != 'process' and existing.is_update_able_from_external():
                input_dict = {'state': 'process'}
                existing.write(input_dict)
            else:
                return existing
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
        sync_strategy = self.get_sync_strategy()
        model_object = self.env[self.internal_model]
        if sync_strategy:
            input_dict = self.get_sync_strategy().prepare_input_external(parent_object, item, **kwargs)

        else:
            _fields = model_object._fields

            input_dict = {}
            # include_fields = self.get_include_fields()
            # exclude_fields = self.get_exclude_fields()
            # mapping_fields = self.get_mapping_fields()
            # exclude_fields.extend([m.key_name for m in mapping_fields.values()])
            # exclude_fields.extend(mapping_fields.keys())

            fields_write_able = model_object.check_field_access_rights('write', None)

            for k, v in item.items():
                if k not in fields_write_able or k not in _fields:
                    continue
                f = _fields[k]

                if f.type == 'boolean':
                    input_dict[k] = bool(v)
                    continue
                if not v:
                    continue
                if f.type in ['many2one', 'one2many', 'many2many']:
                    if not f.required:
                        continue

                    v = parent_object.get_related_data(f, v)
                    if not v:
                        continue
                elif f.type in ['date', 'datetime']:
                    if isinstance(v, str):
                        v = fields.Date.from_string(v) if f.type == 'date' else fields.Datetime.from_string(v)

                input_dict[k] = v

        if is_callable_method(model_object, 'prepare_input_dict'):
            input_dict.update(model_object.prepare_input_dict(item, input_dict=input_dict))

        return input_dict

    def is_update_able_from_external(self):
        return self.sync_strategy_id.is_update_able_from_external()

    def is_create_able_from_external(self):
        return self.sync_strategy_id.is_create_able_from_external()

    def write_done_internal_odoo(self, internal_odoo):
        if internal_odoo:
            self.write({
                'internal_odoo_id': internal_odoo.id,
                'state': 'done',
                'last_success': fields.Datetime.now(),
                'last_processing_datetime': fields.Datetime.now()
            })
        return internal_odoo

    def process_data(self):
        try:
            ModelObject = self.env[self.internal_model]
            item = json.loads(self.data_json)
            internal_odoo_id = self.internal_odoo_id
            if not internal_odoo_id:
                internal_odoo = self.sync_strategy_id.internal_lookup(item)
                if internal_odoo:
                    self.write_done_internal_odoo(internal_odoo)
                    internal_odoo_id = internal_odoo.id
            if internal_odoo_id:
                if not self.is_update_able_from_external():
                    return
            elif not self.is_create_able_from_external():
                return

            if not item or not isinstance(item, dict):
                item = self.get_json_data_for_create()

            if is_callable_method(ModelObject, self.sync_strategy_id.internal_process_method):
                method = getattr(ModelObject, self.sync_strategy_id.internal_process_method)
                existing = method(item, sync_strategy=self.sync_strategy_id, data_sync=self)
                self.write_done_internal_odoo(existing)
            else:
                input_dict = self.prepare_input_external(item)
                if self.is_all_related_done():
                    if internal_odoo_id:
                        existing = ModelObject.browse(internal_odoo_id)
                    else:
                        existing = ModelObject.browse()
                    if existing:
                        existing.write(input_dict)
                    else:
                        internal_context = self.get_internal_context()
                        existing = ModelObject.with_context(internal_context).create([input_dict])[0]
                    self.write_done_internal_odoo(existing)
                else:
                    _logger.info("Delay proses data karena masih ada related data yang belum selesai. (%s) [%s] %s"
                                 , self.internal_model, self.external_model, self.external_odoo_id)

            if self.state == 'done':
                after_create = {}
                for r in self.related_ids:
                    if r.field_after_create:
                        r.process_data()
                        data_relation = r.get_data_relation()
                        if data_relation:
                            after_create[r.name] = data_relation
                if after_create:
                    existing.write(after_create)
        except BaseException as ex:
            self._cr.rollback()
            stack_trace = traceback.format_exc()
            self.write({
                'error_info': stack_trace,
                'state': 'error',
                'last_error': fields.Datetime.now(),
                'last_processing_datetime': fields.Datetime.now(),
                'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
            })
        finally:
            if self.is_all_related_done() and self.state == 'process':
                self.state = 'need_resolve'
            self._cr.commit()

    def action_process_data(self):
        self.process_data()

    def action_open_internal(self):
        self.ensure_one()
        return {
            'name': _('Data Internal Data'),
            'type': 'ir.actions.act_window',
            'res_model': self.internal_model,
            'res_id': self.internal_odoo_id,
            'view_mode': 'form',
        }

    def action_get_json_data_for_create(self):
        self.ensure_one()
        self.data_json = json.dumps(self.get_external_one_data())

    def cron_process_data(self, limit=100):
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        to_process = self.search(
            [('state', '!=', 'done'),
             '|',
             ('last_processing_datetime', '<=', fields.Datetime.now()),
             ('last_processing_datetime', '=', False)],
            limit=limit, order='last_processing_datetime asc,id asc'
        )
        for t in to_process:
            try:
                t.process_data()
            except Exception:
                self._cr.rollback()
                t.write({
                    'error_info': traceback.format_exc(),
                    'state': 'error',
                    'last_error': fields.Datetime.now(),
                    'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                })
            if fields.Datetime.now() > limit_time:
                break

        return True

    def get_internal_context(self):
        return self.sync_strategy_id.get_internal_context()

    def get_internal_object(self):
        if self.internal_model:
            model = self.env[self.internal_model]
            if self.internal_odoo_id:
                return model.browse(self.internal_odoo_id)
            return model
        return None


class ExternalDataSyncRelated(models.Model):
    _name = 'external.data.sync.related'

    external_data_sync_id = fields.Many2one('external.data.sync', ondelete='cascade')
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
    )
    external_app_name = fields.Char(related='external_data_sync_id.external_app_name')
    name = fields.Char()
    internal_model = fields.Char()
    inverse_field = fields.Char()
    field_after_create = fields.Boolean()
    field_type = fields.Selection(
        [('many2one', 'Many2one'), ('one2many', 'One2many'), ('many2many', 'Many2many')],
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('process', 'Process'), ('error', 'Error'), ('done', 'Done'), ]
    )
    data_json = fields.Text()
    internal_data_eval = fields.Text()

    def process_data(self):
        try:
            item = json.loads(self.data_json)
            self.field_after_create = self.external_data_sync_id.internal_model == self.internal_model
            if self.field_type == 'many2one':
                external_data_sync = self.external_data_sync_id.relation_from_external(item, self)
                if external_data_sync:
                    if self.field_after_create and external_data_sync.state != 'done':
                        return  # untuk menghindari loop

                    external_data_sync.process_data()
                    if external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                        self.internal_data_eval = str(external_data_sync.internal_odoo_id)
                        self.state = 'done'

            elif self.field_type == 'many2many':
                if not isinstance(item, list):
                    item = [item]
                internal_ids = []
                for i in item:
                    external_data_sync = self.external_data_sync_id.relation_from_external(i, self)
                    if external_data_sync:
                        self.field_after_create = self.external_data_sync_id.id == external_data_sync.id
                        if self.field_after_create and external_data_sync.state != 'done':
                            return  # untuk menghindari loop

                        external_data_sync.process_data()
                        if external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                            internal_ids.append(external_data_sync.internal_odoo_id)
                            continue
                    internal_ids.append(None)
                if internal_ids and all(isinstance(i, int) for i in internal_ids):
                    self.internal_data_eval = str((6, 0, [internal_ids]))  # replace relasi dengan daftar ID baru
                    self.state = 'done'
            elif self.field_type == 'one2many':
                # todo untuk update one2many
                if self.field_after_create:
                    ids = []
                    for i in item:
                        external_data_sync = self.external_data_sync_id.relation_from_external(i, self)
                        ids.append(external_data_sync)

                    for external_data_sync in ids:
                        if not external_data_sync or external_data_sync.id == self.external_data_sync_id.id or external_data_sync.internal_odoo_id or external_data_sync.state == 'done':
                            continue
                        external_data_sync.process_data()
                else:
                    internal_ids = [(5, 0, 0)]  # → clear semua relasi
                    InternalModel = self.env[self.internal_model]
                    has_external_odoo_id = 'external_odoo_id' in InternalModel._fields
                    if not isinstance(item, list):
                        item = [item]
                    for d in item:
                        external_odoo_id = d.pop('id')
                        if has_external_odoo_id and self.external_data_sync_id.internal_odoo_id:
                            domain = [
                                ('external_odoo_id', '=', external_odoo_id),
                                (self.inverse_field, '=', self.external_data_sync_id.internal_odoo_id)
                            ]
                            existing = InternalModel.search(domain, limit=1)
                            if existing:
                                d['external_odoo_id'] = external_odoo_id
                                internal_ids.append((1, existing.id, d))  # update record yang sudah ada
                                continue
                        internal_ids.append((0, 0, d))  # buat record baru & link
                    self.internal_data_eval = str(internal_ids)
                    self.state = 'done'

        except Exception:
            stack_trace = traceback.format_exc()
            self.write({
                'state': 'error',
                'internal_data_eval': None,
            })
            _logger.error("Error process related data %s : %s", self.name, stack_trace)

    def get_data_relation(self):
        if self.state != 'done':
            self.process_data()
        if self.state == 'done' and self.internal_data_eval:
            return ast.literal_eval(self.internal_data_eval)

        return None
