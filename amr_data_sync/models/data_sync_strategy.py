# -*- coding: utf-8 -*-

import ast
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import traceback
import logging
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


def is_callable_method(model, method):
    return hasattr(model, method) and callable(getattr(model, method))


class ExternalDataSync(models.Model):
    _name = 'external.data.sync.strategy'
    _description = """
    Model strategy bagaimana objec di syncronkan dari server external
    """
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    external_model = fields.Char()
    external_app_name = fields.Char()
    external_domain = fields.Char()
    external_context = fields.Char()
    external_fields = fields.Char()
    internal_model = fields.Char()
    internal_lookup_fields = fields.Char()
    exclude_fields = fields.Char()
    after_create_fields = fields.Char(
        help="Field yang akan di proses setelah create karena kemungkin rekursif. contoh: parent_id"
    )
    relation_field_ignore = fields.Boolean()

    company_id = fields.Many2one(
        'res.company'
    )
    server_sync_id = fields.Many2one(
        'external.server.sync'
    )
    next_sync_datetime = fields.Datetime()
    last_sync_datetime = fields.Datetime()
    sync_cron = fields.Boolean()
    strategy = fields.Selection([
        ('local_lookup', 'Local Lookup'),
        ('external_cud', 'Create Update Delete'),
        ('external_cu', 'Create Update'),
        ('external_create', 'Create'),
    ], help="""
    Lookup strategery
    """)

    external_sync = fields.Selection([
        ('jsonrpc', 'Json-RPC'),
        ('method_call', 'Method Call'),
    ], default='jsonrpc')

    parent_sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        string='Parent Data Sync',
        help="Parent data sync ini di gunakan untuk related object bila di perlukan."
             "Bila mempunyai parent maka server_sync_id dan external_app_name akan mengikuti parent"
    )
    parent_field_name = fields.Char()
    line_sync_strategy_ids = fields.One2many(
        'external.data.sync.strategy',
        'parent_sync_strategy_id',
    )
    line_mapping_ids = fields.One2many(
        'external.data.mapping',
        'sync_strategy_id',
    )
    eval_script = fields.Text()

    internal_lookup_method = fields.Char()
    internal_prepare_method = fields.Char()
    internal_context = fields.Char()
    internal_process_method = fields.Char(
        help="Method ini di panggil setelah data di proses dari external dan sebelum di simpan ke internal"
    )
    internal_call_method = fields.Char(
        help="Method ini di panggil setelah data di proses dari external dan sebelum di simpan ke internal"
    )

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'server_sync_id' in vals and vals['server_sync_id']:
                server = self.server_sync_id.browse(vals['server_sync_id'])
                if not server:
                    raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
                vals['external_app_name'] = server.app_name

        return super(ExternalDataSync, self).create(vals_list)

    def write(self, vals):
        if 'server_sync_id' in vals and vals['server_sync_id']:
            server = self.server_sync_id.browse(vals['server_sync_id'])
            if not server:
                raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
            vals['external_app_name'] = server.app_name

        return super(ExternalDataSync, self).write(vals)

    def get_server_sync(self):
        return self.server_sync_id or self.server_sync_id.search([('app_name', '=', self.external_app_name)], limit=1)

    def is_delete_able_from_external(self):
        return self.strategy in ['external_cud']

    def is_update_able_from_external(self):
        return self.strategy in ['external_cud', 'external_cu']

    def is_create_able_from_external(self):
        return self.strategy in ['external_cud', 'external_cu', 'external_create']

    def get_include_fields(self):
        include_fields = []
        if self.external_fields:
            include_fields = [p.strip() for p in self.external_fields.split(",")]
        return include_fields

    def get_mapping_fields(self):
        #env = self.env
        mapping_list = self.line_mapping_ids.filtered(lambda m: m.internal_field and  m.mapping_strategy=='field_mapping')

        # env['external.data.mapping'].search([
        #     ('sync_strategy_id', '=', self.id),
        #     ('internal_model', '=', self.internal_model),
        #     ('mapping_strategy', '=', 'field_mapping'),
        #     ('internal_field', '!=', False)]
        # )
        return {
            m.internal_field: m for m in mapping_list
        }

    def get_after_create_fields(self):
        after_create_fields = []
        if self.after_create_fields:
            after_create_fields = [p.strip() for p in self.after_create_fields.split(",")]
        return after_create_fields

    def get_exclude_fields(self):
        exclude_fields = ['self']
        env = self.env
        # todo ambil dari configurasi
        exclude_fields.extend(env['mail.thread']._fields.keys())
        exclude_fields.extend(env['mail.activity.mixin']._fields.keys())
        exclude_fields.extend(env['mail.blacklist']._fields.keys())

        return exclude_fields

    def get_internal_lookup_fields(self):
        field_list = []
        if self.internal_lookup_fields:
            field_list = [p.strip() for p in self.internal_lookup_fields.split(",")]
        return field_list

    def get_external_fields(self):
        field_list = []
        if self.external_fields:
            field_list = [p.strip() for p in self.external_fields.split(",")]
        return field_list

    def action_sync_now(self):
        return self.sync_from_application_server()

    def get_external_one_data(self, object_id):
        context = None
        fields = None
        if self.external_context:
            context = ast.literal_eval(self.external_context)
        if self.external_fields:
            fields = self.get_external_fields()
        result = self.ensure_one().get_server_sync().get_external_data(
            self.external_model, fields=fields,object_id=object_id, context=context
        )
        return result and result[0]

    def internal_lookup(self, item):
        Model = self.env[self.internal_model].sudo()
        if is_callable_method(Model, self.internal_lookup_method):
            method = getattr(Model, self.internal_lookup_method)
            return method(item)

        internal_lookup_fields = self.get_internal_lookup_fields()
        if not internal_lookup_fields:
            internal_lookup_fields = ['name']

        _fields = Model._fields
        domain = []
        for f in internal_lookup_fields:
            if f in _fields and f in item:
                domain.append((f, '=', item[f]))

        return Model.search(domain, limit=1)

    def lookup_strategy(self, internal_model, parent_sync_strategy=None, server_sync=None, external_app_name=None):
        if parent_sync_strategy:
            strategy = self.search([
                ('internal_model', '=', internal_model),
                ('parent_sync_strategy_id', '=', parent_sync_strategy.id),
            ], limit=1)
            server_sync = parent_sync_strategy.get_server_sync() or server_sync

        if not strategy and server_sync:
            strategy = self.search([
                ('internal_model', '=', internal_model),
                ('server_sync_id', '=', server_sync.id),
            ], limit=1)

            external_app_name = server_sync.app_name or external_app_name

        if not strategy and external_app_name:
            strategy = self.search([
                ('internal_model', '=', internal_model),
                ('external_app_name', '=', external_app_name),
            ], limit=1)

        return strategy or self.browse()

    def prepare_input_external(self, parent_object, item, **kwargs):
        model_object = self.env[self.internal_model]
        _fields = model_object._fields

        input_dict = {}
        include_fields = self.get_include_fields()
        exclude_fields = self.get_exclude_fields()
        mapping_fields = self.get_mapping_fields()
        after_create_fields = self.get_after_create_fields()
        exclude_fields.extend([m.key_name for m in mapping_fields.values()])
        exclude_fields.extend(mapping_fields.keys())

        fields_write_able = model_object.check_field_access_rights('write', None)

        for k, v in item.items():
            if k not in fields_write_able or k not in _fields or k in exclude_fields:
                continue
            f = _fields[k]

            if f.compute or f.related:
                continue

            if f.type == 'boolean':
                input_dict[k] = bool(v)
                continue
            if not v:
                continue

            if f.type in ['many2one', 'one2many', 'many2many']:
                if k in include_fields:
                    _logger.info("Process relation field %s.%s", self.internal_model, k)
                elif not f.required and self.relation_field_ignore:
                    continue
                v = parent_object.get_related_data(f, v)
                if not v or k in after_create_fields:
                    continue
            elif f.type in ['date', 'datetime']:
                if isinstance(v, str):
                    v = fields.Date.from_string(v) if f.type == 'date' else fields.Datetime.from_string(v)

            input_dict[k] = v

        for k, m in mapping_fields.items():
            if k in fields_write_able and k in _fields:
                input_dict[k] = m.mapping_data(item, model=model_object)

        if self.eval_script:
            try:
                eval_context = {'env': self.env, 'model': model_object, 'external_data': item}
                safe_eval(self.eval_script.strip(), eval_context, mode="exec",
                          nocopy=True,
                          filename=str(self))  # nocopy allows to return 'action'
                eval_context.get('value')
            except Exception as e:
                raise ValueError(f"Error evaluating script: {e}")

        return input_dict

    def sync_from_application_server(self):
        if self.external_sync == 'jsonrpc':
            self.jsonrcp_sync_from_application_server()

    @api.model
    def jsonrcp_sync_from_application_server(self):
        self.ensure_one()
        server_sync = self.get_server_sync()
        offset = 0
        row_count = limit = 100
        self.write({
            'last_sync_datetime': fields.Datetime.now(),
        })

        domain = []
        if self.external_domain:
            domain = ast.literal_eval(self.external_domain)
        context = {}
        if self.external_context:
            context = ast.literal_eval(self.external_context)
        total = server_sync.get_external_data(self.external_model, domain, count=True)
        fields_list = ['display_name', 'name', 'write_date', 'id'] + self.get_internal_lookup_fields()

        while total and row_count == limit:
            data = server_sync.get_external_data(
                self.external_model, domain, fields=fields_list, offset=None, limit=None, context=context)
            row_count = len(data) if data else 0
            if row_count == 0:
                break
            _logger.info("Count %s ,Offset %s, Total: %s", len(data), offset, total)
            for item in data:
                offset = offset + 1
                self.env['external.data.sync'].data_from_external(
                    item, self
                )

        _logger.info("Offset %s = total %s", offset, total)
        self.write({
            'next_sync_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
        })

    def cron_sync_from_server(self):
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
        data_sync_models = self.search([
            ('active', '=', True),
            ('sync_cron', '=', True),
            ('strategy', 'in', ['external_cud', 'external_cu', 'external_create']),
            ('parent_sync_strategy_id', '=', False),
            '|',
            ('next_sync_datetime', '<=', fields.Datetime.now()),
            ('next_sync_datetime', '=', False),
        ])
        for data_sync in data_sync_models:
            try:
                data_sync.sync_from_application_server()
            except Exception as e:
                _logger.error(
                    "Error sync from server %s , model %s : %s",
                    data_sync.external_app_name,
                    data_sync.external_model,
                    traceback.format_exc()
                )
            if fields.Datetime.now() > limit_time:
                break

    def get_internal_context(self):
        return self.internal_context and ast.literal_eval(self.internal_context) or {}
