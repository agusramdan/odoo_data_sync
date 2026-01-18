# -*- coding: utf-8 -*-

from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
from ..tools.utils import is_callable_method, get_callable_method, convert_from_external_data
from odoo.addons.amr_jsonrpc import jsonrpc, rest
import ast
import logging

_logger = logging.getLogger(__name__)


class ExternalDataSyncStrategy(models.Model):
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
    external_company_name = fields.Char()
    external_domain = fields.Char()
    external_context = fields.Char()
    external_fields = fields.Char()

    internal_model = fields.Char()
    internal_lookup_fields = fields.Char()
    exclude_fields = fields.Char()
    after_create_fields = fields.Char(
        help="Field yang akan di proses setelah create karena kemungkin rekursif. contoh: parent_id"
    )
    relation_strategy = fields.Selection([
        ('ignore', 'Ignore'),
        ('to_many_ignore', 'To Many Ignore'),
        ('parent_ignore', 'Parent Ignore'),
        ('to_one_ignore', 'To Ignore'),
        ('all_process', 'All Process'),
    ], default='parent_ignore')
    relation_field_ignore = fields.Boolean()

    company_id = fields.Many2one(
        'res.company',
        help="Default Company"
    )
    server_sync_id = fields.Many2one(
        'external.server.sync'
    )
    filter_last_update = fields.Boolean()
    # next_sync_datetime = fields.Datetime()
    # last_sync_datetime = fields.Datetime()
    # sync_cron = fields.Boolean()
    strategy = fields.Selection([
        ('local_lookup', 'Local Lookup'),
        ('external_cud', 'Create Update Delete'),
        ('external_cu', 'Create Update'),
        ('external_create', 'Create Only'),
        ('external_update', 'Update Only'),
    ], help="""
    Strategy
    """)
    # 'Update Only'
    internal_id_same_as_external = fields.Boolean()
    internal_id_offset = fields.Integer()
    external_sync = fields.Selection([
        ('jsonrpc', 'Json-RPC'),
        ('rest', 'Rest'),
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
        help="Method ini di panggil untuk option call_method"
    )
    sync_cron = fields.Boolean()

    test_external_data_sync_id = fields.Many2one(
        'external.data.sync',
        ondelete='set null'
    )

    def is_relation_ignore(self):
        return self.relation_strategy == 'ignore'

    def is_relation_to_many_ignore(self):
        return self.is_relation_ignore() or self.relation_strategy == 'to_many_ignore'

    def is_relation_parent_ignore(self):
        return self.is_relation_to_many_ignore() or self.relation_strategy == 'parent_ignore'

    def is_relation_to_one_ignore(self):
        return self.is_relation_parent_ignore() or self.relation_strategy == 'to_one_ignore'

    def action_test_execute_eval(self, external_data, prepare_dict):
        if not self.test_external_data_sync_id:
            raise UserError(_("Please select one data."))

        self.execute_prepare_eval(external_data, prepare_dict)

    def name_get(self):
        result = []
        for rec in self:
            name = f"({rec.id}) [{rec.get_external_application_name()}] {rec.external_model} -> {rec.internal_model}"
            result.append((rec.id, name))
        return result

    def get_external_sync(self):
        return self.external_sync

    def get_external_application_name(self):
        return self.server_sync_id.get_application_name() or self.external_app_name

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_name' in vals:
                company_name = vals.pop('company_name')
                if company_name and isinstance(company_name, str):
                    company = self.env['res.company'].search([('name', 'ilike', company_name)], limit=1)
                    if company:
                        vals['company_id'] = company.id
                    else:
                        vals['company_id'] = False
            if 'server_sync_id' in vals and vals['server_sync_id']:
                server = self.server_sync_id.browse(vals['server_sync_id'])
                if not server:
                    raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
                vals['external_app_name'] = server.get_application_name()

        result = super(ExternalDataSyncStrategy, self).create(vals_list)

        if self._context.get('__from_sync_cron'):
            return result

        for rec in result:
            if rec.sync_cron:
                sync_cron = self.env['external.data.sync.cron'].with_context(active_test=False).search(
                    [('sync_strategy_id', '=', rec.id)], limit=1)
                if not sync_cron:
                    self.env['external.data.sync.cron'].create({
                        'sync_strategy_id': rec.id,
                        'active': rec.sync_cron
                    })
                elif sync_cron.active != rec.sync_cron:
                    sync_cron.write({
                        'active': rec.sync_cron
                    })
        return result

    def write(self, vals):

        if 'company_name' in vals:
            company_name = vals.pop('company_name')
            if company_name and isinstance(company_name, str):
                company = self.env['res.company'].search([('name', 'ilike', company_name)], limit=1)
                if company:
                    vals['company_id'] = company.id
        if 'server_sync_id' in vals and vals['server_sync_id']:
            server = self.server_sync_id.browse(vals['server_sync_id'])
            if not server:
                raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
            vals['external_app_name'] = server.get_application_name()

        result = super(ExternalDataSyncStrategy, self).write(vals)
        if self._context.get('__from_sync_cron'):
            return result
        for rec in self:
            if 'sync_cron' in vals:
                sync_cron = self.env['external.data.sync.cron'].with_context(active_test=False).search(
                    [('sync_strategy_id', '=', rec.id)], limit=1)
                if not sync_cron and vals['sync_cron']:
                    self.env['external.data.sync.cron'].create({
                        'sync_strategy_id': rec.id,
                        'active': vals['sync_cron']
                    })
                elif sync_cron and sync_cron.active != vals['sync_cron']:
                    sync_cron.write({
                        'active': vals['sync_cron']
                    })

        return result

    def get_server_sync(self):
        return self.server_sync_id or self.server_sync_id.search([('app_name', '=', self.external_app_name)], limit=1)

    def is_delete_able_from_external(self):
        return self.strategy in ['external_cud']

    def is_update_able_from_external(self):
        return self.strategy in ['external_cud', 'external_cu', 'external_update']

    def is_update_only_from_external(self):
        return self.strategy == 'external_update'

    def is_create_able_from_external(self):
        return self.strategy in ['external_cud', 'external_cu', 'external_create']

    def get_include_fields(self):
        include_fields = []
        if self.external_fields:
            include_fields = [p.strip() for p in self.external_fields.split(",")]
        return include_fields

    def get_mapping_fields(self):
        mapping_list = self.line_mapping_ids.filtered(
            lambda m: m.internal_field
        )
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
        exclude_fields.extend(env['external.data.sync.exclude'].get_exclude_all_fields())
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
        ModelObject = self.sync_one_model_object(object_id)
        result = ModelObject.read()
        if result and isinstance(result, list):
            return result[0]
        return result

    def internal_lookup(self, item):
        item_data = convert_from_external_data(item)
        external_id = item_data.get('id')
        display_name = item_data.get('display_name')

        Model = self.env[self.internal_model].sudo()
        if self.strategy == 'external_update' and external_id:
            if self.internal_id_same_as_external:
                return Model.search([('id', '=', external_id)])
            if self.internal_id_offset > 0:
                return Model.search([('id', '=', external_id + self.internal_id_offset)])

        Model = self.env[self.internal_model].sudo()
        if is_callable_method(Model, self.internal_lookup_method):
            method = getattr(Model, self.internal_lookup_method)
            return method(item, sync_strategy=self)

        data_lookup = self.env['external.data.lookup'].lookup_internal(
            self.get_external_application_name(), self.external_model, self.internal_model,
            external_id, display_name
        )

        if data_lookup:
            return data_lookup

        internal_lookup_fields = self.get_internal_lookup_fields()
        if internal_lookup_fields:
            _fields = Model._fields
            domain = []
            for f in internal_lookup_fields:
                if f in _fields and f in item:
                    domain.append((f, '=', item[f]))
            return Model.search(domain, limit=1)
        else:
            return Model.browse()

    def lookup_strategy(
            self, internal_model,
            parent_sync_strategy=None,
            server_sync=None,
            external_app_name=None,
            external_model=None
    ):
        if parent_sync_strategy:
            strategy = self.search([
                ('external_model', '=', external_model),
                ('internal_model', '=', internal_model),
                ('parent_sync_strategy_id', '=', parent_sync_strategy.id),
            ], limit=1)
            server_sync = parent_sync_strategy.get_server_sync() or server_sync

        if not strategy and server_sync:
            strategy = self.search([
                ('external_model', '=', external_model),
                ('internal_model', '=', internal_model),
                ('server_sync_id', '=', server_sync.id),
            ], limit=1)

            external_app_name = server_sync.get_application_name() or external_app_name

        if not strategy and external_app_name:
            strategy = self.search([
                ('external_model', '=', external_model),
                ('internal_model', '=', internal_model),
                ('external_app_name', '=', external_app_name),
            ], limit=1)

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

        related_data_process_after_mapping = {}
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
                related_data_process_after_mapping[k] = (f, v)
                continue

            elif f.type in ['date', 'datetime']:
                if isinstance(v, str):
                    v = fields.Date.from_string(v) if f.type == 'date' else fields.Datetime.from_string(v)

            input_dict[k] = v
        for k, m in mapping_fields.items():
            if k in fields_write_able and k in _fields:
                field = _fields[k]
                input_dict[k] = m.mapping_data(item, model=model_object, parent_data_sync=parent_object, field=field)
        eval_script = self.eval_script and self.eval_script.strip()
        if eval_script:
            try:
                eval_context = {'env': self.env, 'model': model_object, 'external_data': item, 'input_dict': input_dict}
                # nocopy allows to return 'action'
                safe_eval(self.eval_script.strip(), eval_context, mode="exec", nocopy=True)
                input_dict.update(eval_context.get('input_dict') or {})
            except Exception as e:
                raise ValueError(f"Error evaluating script: {e}")

        # relation check
        for k, m in related_data_process_after_mapping.items():
            f, v = m
            if f.name in input_dict:
                continue
            v = parent_object.get_related_data(f, v)
            if not v or k in after_create_fields:
                continue
            input_dict[k] = v

        return input_dict

    def sync_from_application_server(self):
        external_sync = self.get_external_sync()
        if external_sync == 'method_call':
            self.method_call_sync_from_application_server()
        else:
            self.sync_list_model_object()

    def get_db_uid_username_password(self):
        return self.server_sync_id.get_db_uid_username_password()

    def jsonrpc_endpoint_url(self):
        return self.server_sync_id.jsonrpc_endpoint_url()

    def get_endpoint_url(self):
        external_sync = self.get_external_sync()
        if external_sync == 'jsonrpc':
            return self.jsonrpc_endpoint_url()
        return self.server_sync_id.get_endpoint_url()

    def prepare_sync_list_dict(self):
        # context
        context = {}
        if self.external_context:
            context = ast.literal_eval(self.external_context)
        # domain
        domain = []
        if self.external_domain:
            domain = ast.literal_eval(self.external_domain) or []
        if self.filter_last_update:
            last_sync = self.env['external.data.sync'].get_last_sync_datetime(self)
            if last_sync:
                _logger.info("Filter last update from %s", last_sync)
                domain = [('write_date', '>=', last_sync.strftime('%Y-%m-%d %H:%M:%S'))] + domain

        fields_list = ['display_name', 'name', 'write_date', 'id'] + self.get_internal_lookup_fields()
        endpoint_url = self.get_endpoint_url()
        config = {
            'endpoint_url': endpoint_url,
            'fields': fields_list,
            'context': context,
            'domain': domain,
        }
        config.update(self.get_auth_config())
        return config

    def get_auth_config(self, config=None):
        auth_type = self.server_sync_id.auth_type
        token_key = self.server_sync_id.token_key
        access_token = self.server_sync_id.token_value
        if auth_type == 'token':
            auth_type = self.server_sync_id.token_in
        db, uid, username, password = self.get_db_uid_username_password()
        return {
            'db': db,
            'uid': uid,
            'username': username,
            'password': password,
            'auth_mode': auth_type,
            'token_key': token_key,
            'access_token': access_token,
            'token_endpoint_url': None
        }

    def prepare_sync_one_dict(self):
        # context
        context = self.get_external_context()
        # domain
        domain = []
        if self.external_domain:
            domain = ast.literal_eval(self.external_domain) or []
        fields_list = None
        if self.external_fields:
            fields_list = self.get_external_fields()
        endpoint_url = self.get_endpoint_url()
        # todo fix
        config = {
            'endpoint_url': endpoint_url,
            'fields': fields_list,
            'context': context,
            'domain': domain,
        }
        config.update(self.get_auth_config())
        return config

    def remote_model_object(self, external_model, **kwargs):
        external_sync = self.get_external_sync()
        if external_sync == 'jsonrpc':
            return jsonrpc.model_object(external_model, **kwargs)
        elif external_sync == 'rest':
            return jsonrpc.model_object(external_model, **kwargs)
        else:
            raise NotImplementedError(f"External sync {external_sync} not implemented yet")

    def sync_model_object(self, **kwargs):
        return self.remote_model_object(self.external_model, **kwargs)

    def sync_list_model_object(self):
        self.ensure_one()
        kwargs = self.prepare_sync_list_dict() or {}
        return self.sync_model_object(**kwargs)

    def sync_one_model_object(self, object_id):
        self.ensure_one()
        kwargs = self.prepare_sync_one_dict()
        kwargs['ids'] = [object_id]
        return self.sync_model_object(**kwargs)

    def sync_from_application_server(self):
        ModelObject = self.sync_list_model_object()
        self = self.ensure_internal_context()

        def callback(item, **kwargs):
            self.env['external.data.sync'].data_from_external(item, self)

        ModelObject.external_data_callback(callback)

    @api.model
    def method_call_sync_from_application_server(self):
        model = self.env[self.internal_model]
        func = get_callable_method(model, self.internal_call_method)
        return func(self)

    def get_external_context(self):
        return self.external_context and ast.literal_eval(self.external_context) or {}

    def get_internal_context(self):
        return self.internal_context and ast.literal_eval(self.internal_context) or {}

    def ensure_internal_context(self):
        if self:
            set_contex = False
            context = dict(self.env.context)
            if self.company_id:
                set_contex = True
                context.update(default_company_id=self.company_id)
            internal_context = self.get_internal_context()
            if internal_context:
                context.update(internal_context)
            if set_contex:
                self = self.with_context(**context)
        return self

    def execute_prepare_eval(self, external_data, prepare_dict):

        if not self.eval_script:
            return prepare_dict
        eval_script = self.eval_script.strip()
        if not eval_script:
            return prepare_dict
        try:
            model = self.env[self.internal_model]
            eval_context = {
                'env': self.env,
                'model': model,
                'external_data': external_data,
                'sync_strategy': self,
                'prepare': prepare_dict,
            }
            safe_eval(
                eval_script,
                eval_context, mode="exec",
                nocopy=True,  # nocopy allows to return 'prepare'
            )
            return eval_context.get('prepare')
        except Exception as e:
            raise ValueError(f"Error evaluating script: {e}")

    def reverse_mapping(self, internal, raise_not_found_exception=True):
        sync_strategy = self.ensure_one()
        # digunakan untuk mengirim data ke server external
        if not internal:
            return [0]

        if not isinstance(internal, models.BaseModel):
            _logger.error("Internal Object must")
            if raise_not_found_exception:
                raise ValueError("Internal Object must")
            return [0]

        domain = [('internal_odoo_id', 'in', internal.ids), ('sync_strategy_id', '=', sync_strategy.id)]

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

    def get_internal_id_same_as_external(self, item):
        item_dict = {}
        if isinstance(item, list):
            if len(item) > 0:
                item_dict['id'] = item[0]
            if len(item) > 1:
                item_dict['name'] = item[1]
        elif isinstance(item, dict):
            item_dict = item
        external_id = item_dict.get('id')
        if self.internal_id_offset:
            external_id += self.internal_id_offset
        if external_id and self.internal_id_same_as_external:
            return external_id
        return None

    def get_or_create_relation_from_external(self, list_of_int_or_dict, sync_related):
        # Create for many2many or one2many
        pass
