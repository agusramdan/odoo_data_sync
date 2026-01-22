# -*- coding: utf-8 -*-

import ast
import datetime
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import date_utils
from ..tools.utils import is_callable_method
from odoo.addons.amr_jsonrpc.utils import savepoint

import json
import traceback
import logging

_logger = logging.getLogger(__name__)


class ExternalDataSyncRelated(models.Model):
    _name = 'external.data.sync.related'

    external_data_sync_id = fields.Many2one(
        'external.data.sync',
        ondelete='cascade'
    )
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        ondelete='set null'
    )
    external_app_name = fields.Char(related='external_data_sync_id.external_app_name')
    name = fields.Char("Field")
    internal_model = fields.Char()
    inverse_field = fields.Char(
        help='For one2many Relation'
    )
    field_after_create = fields.Boolean()
    field_type = fields.Selection(
        [('many2one', 'Many2one'), ('one2many', 'One2many'), ('many2many', 'Many2many')],
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('process', 'Process'), ('error', 'Error'), ('done', 'Done'), ]
    )
    data_json = fields.Text()
    internal_data_eval = fields.Text()
    related_external_data_sync_id = fields.Many2one(
        'external.data.sync',
        ondelete='set null'
    )
    mandatory_before_create = fields.Boolean()
    next_processing_datetime = fields.Datetime()

    def get_All_data_relation(self):
        if self.env.context.get("__try_process_relation"):
            _logger.info("Avoid recursive")
            return
        result = {}
        for related in self.with_context(__try_process_relation=True):
            value = related.get_data_relation()
            if value:
                result[related.name] = value
        return result

    def action_process_data(self):
        self.try_process_data()

    def try_process_data(self):
        if self.env.context.get("__try_process_relation"):
            _logger.info("Avoid recursive")
            return
        for related in self.with_context(__process_relation=True, __try_process_relation=True):
            related.process_data()

    @savepoint
    def process_field_after_create(self):
        if self.env.context.get("__process_relation") or self.env.context.get("__process_field_after_create"):
            _logger.info(f"rekursif terdekteksi {self.name} , {self.internal_model}")
            return
        self.with_context(__process_relation=True, __process_field_after_create=True).process_data()

    @savepoint
    def process_data(self):
        try:
            if not self.data_json:
                return
            item = json.loads(self.data_json)
            if self.field_type == 'many2one':
                if self.related_external_data_sync_id:
                    external_data_sync = self.related_external_data_sync_id
                elif item:
                    external_data_sync = self.related_external_data_sync_id.relation_from_external(item, self)
                    self.related_external_data_sync_id = external_data_sync
                    if self.related_external_data_sync_id == external_data_sync:
                        # cirular
                        self.internal_data_eval = str(external_data_sync.internal_odoo_id)
                        self.state = 'done'
                        return
                else:
                    return
                if external_data_sync:
                    if external_data_sync.state != 'done' and not self.field_after_create \
                            and self.env.context.get("__process_relation"):
                        external_data_sync.process_data()

                    if external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                        self.internal_data_eval = str(external_data_sync.internal_odoo_id)
                        self.state = 'done'
                        return
                elif item:
                    # using data lookup
                    data = self.internal_lookup(item)
                    if data:
                        self.internal_data_eval = str(data.id)
                        self.state = 'done'
            elif item:
                if self.field_type in ['many2many', 'one2many']:
                    # pada tuple command ditambahkan informasi external id
                    if not item:
                        return
                    internal_ids = []
                    if self.sync_strategy_id:
                        external_data_sync_list = self.sync_strategy_id.get_or_create_relation_from_external(item, self)
                        for external_data_sync in external_data_sync_list:
                            if external_data_sync and external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                                internal_ids.append(external_data_sync.internal_odoo_id)
                                continue
                            internal_ids.append(None)
                    if internal_ids and all(isinstance(i, int) for i in internal_ids):
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
            self.try_process_data()
        if self.state == 'done':
            if self.field_type == 'many2one' and self.related_external_data_sync_id:
                return self.related_external_data_sync_id.internal_odoo_id or None
            if self.internal_data_eval:
                return ast.literal_eval(self.internal_data_eval) or None

        return None

    def create_or_get_related(
            self,
            external_data_sync_id, field_name, field_type,
            field_required=False,
            inverse_field=None,
            related_sync_strategy_id=None,
            related_external_data_sync_id=None,
            internal_model=None,
            value=None
    ):
        # value for this related related_external_data_sync_id
        # parent external_data_sync_id
        if field_name=='resource_id':
            print("ddd")
        field_after_create = field_type in ['many2many', 'one2many']
        update = {
            'field_after_create': field_after_create,
            'field_type': field_type
        }

        if related_sync_strategy_id:
            internal_model = related_sync_strategy_id.internal_model
            update['sync_strategy_id'] = related_sync_strategy_id.id,
            update['internal_model'] = internal_model
            update['field_after_create'] = external_data_sync_id.internal_model == internal_model
        else:
            update['internal_model'] = internal_model
        if inverse_field:
            update['inverse_field'] = inverse_field

        if field_required:
            update['field_after_create'] = False
            update['mandatory_before_create'] = True
        if value:
            update['data_jason'] = json.dumps(value, default=date_utils.json_default)
        if related_external_data_sync_id:
            update['related_external_data_sync_id'] = int(related_external_data_sync_id)
        domain = [
            ('external_data_sync_id', '=', int(external_data_sync_id)),
            ('name', '=', field_name),
        ]
        existing = self.search(domain, limit=1)
        if existing:
            existing.write(update)
            return existing

        create_dict = {
            'name': field_name,
            'external_data_sync_id': int(external_data_sync_id),
            'state': 'draft',
        }
        create_dict.update(update)
        return self.create([create_dict])[0]

    # def get_or_create(
    #         self, related_external_data_sync_id, external_data_sync_id, field_name, field_type,
    #         inverse_field=None, required_before_create=False, related_sync_strategy_id=False,
    #
    # ):
    #     # value for this related related_external_data_sync_id
    #     # parent external_data_sync_id
    #     if required_before_create:
    #         field_after_create = False
    #     elif related_sync_strategy_id:
    #         field_after_create = external_data_sync_id.internal_model == related_sync_strategy_id.internal_model
    #
    #     domain = [
    #         ('external_data_sync_id', '=', int(external_data_sync_id)),
    #         ('name', '=', field_name),
    #         ('field_type', '=', field_type),
    #     ]
    #     related = int(related_external_data_sync_id)
    #     if related:
    #         existing = self.search(domain + [('related_external_data_sync_id', '=', related)], limit=1)
    #         if existing:
    #             return existing
    #
    #     existing = self.search(domain + [('related_external_data_sync_id', '=', False)], limit=1)
    #
    #     if existing and related:
    #         existing.write({
    #             'related_external_data_sync_id': related
    #         })
    #         return existing
    #
    #     create_dict = {
    #         'name': field_name,
    #         'field_after_create': field_after_create,
    #         'internal_model': related_external_data_sync_id.internal_model,
    #         'external_data_sync_id': int(external_data_sync_id),
    #         'field_type': field_type,
    #         'inverse_field': inverse_field,
    #         'required_before_create': required_before_create,
    #         'related_external_data_sync_id': related or None,
    #
    #     }
    #
    #     return self.create([create_dict])[0]

    def internal_lookup(self, item):
        external_id = None
        display_name = None
        if isinstance(item, dict):
            external_id = item.get('id')
            display_name = item.get('display_name')
        elif isinstance(item, list) and len(item) > 1 and isinstance(item[0], int) and isinstance(item[1], str):
            external_id = item[0]
            display_name = item[1]
        elif isinstance(item, int):
            external_id = item

        internal_model = external_model = self.internal_model
        data = self.env['external.data.lookup'].lookup_internal(
            self.external_app_name, external_model, internal_model,
            external_id=external_id, display_name=display_name
        )

        if data:
            return data

        Model = self.env[self.internal_model].sudo()
        if is_callable_method(Model, "lookup_internal_from_external_data"):
            method = getattr(Model, "lookup_internal_from_external_data")
            return method(item, sync_strategy=self.related_external_data_sync_id.sync_strategy_id)
        return None
