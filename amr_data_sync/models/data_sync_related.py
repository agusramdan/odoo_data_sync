# -*- coding: utf-8 -*-

import ast
import datetime
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..tools.utils import is_callable_method

import json
import traceback
import logging

_logger = logging.getLogger(__name__)


class ExternalDataSyncRelated(models.Model):
    _name = 'external.data.sync.related'

    external_data_sync_id = fields.Many2one(
        'external.data.sync', ondelete='cascade'
    )
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
    )
    external_app_name = fields.Char(related='external_data_sync_id.external_app_name')
    name = fields.Char()
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
    related_external_data_sync_id = fields.Many2one('external.data.sync', ondelete='cascade')
    mandatory_before_create = fields.Boolean()

    def process_data(self):
        try:
            if not self.data_json:
                return
            item = json.loads(self.data_json)
            external_data_sync = self.related_external_data_sync_id.relation_from_external(item, self)
            if external_data_sync:
                self.env.context.get(
                    "__process_relation") and external_data_sync.state != 'done' and external_data_sync.process_data()
                if external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                    self.internal_data_eval = str(external_data_sync.internal_odoo_id)
                    self.state = 'done'
                    return
                elif not self.related_external_data_sync_id:
                    self.related_external_data_sync_id = external_data_sync
            elif item:
                if self.field_type == 'many2one':
                    # using data lookup
                    data = self.internal_lookup(item)
                    if data:
                        self.internal_data_eval = str(data.id)
                        self.state = 'done'
                elif self.field_type == 'many2many':
                    # pada tuple command ditambahkan informasi external id
                    if not item:
                        return
                    if not isinstance(item, list):
                        item = [item]
                    internal_ids = []
                    external_mapping = {}
                    for i in item:
                        external_data_sync = self.external_data_sync_id.relation_from_external(i, self)
                        if external_data_sync:
                            self.env.context.get("__process_relation") and external_data_sync.process_data()
                            if external_data_sync.state == 'done' and external_data_sync.internal_odoo_id:
                                internal_ids.append(external_data_sync.internal_odoo_id)
                                external_mapping[external_data_sync.internal_odoo_id] = i
                                continue
                        internal_ids.append(None)
                    if internal_ids and all(isinstance(i, int) for i in internal_ids):
                        self.internal_data_eval = str((6, 0, [internal_ids], external_mapping))
                        # replace relasi dengan daftar ID baru
                        self.state = 'done'
                elif self.field_type == 'one2many':

                    ids = []
                    for i in item:
                        external_data_sync = self.external_data_sync_id.relation_from_external(i, self)
                        ids.append(external_data_sync)
                    ready = True
                    for external_data_sync in ids:
                        if not external_data_sync or external_data_sync.id == self.external_data_sync_id.id \
                                or external_data_sync.internal_odoo_id or external_data_sync.state == 'done':
                            continue
                        if self.env.context.get("__process_relation"):
                            external_data_sync.process_data()
                            if external_data_sync.state != 'done':
                                ready = False
                    if ready:
                        internal_ids = []
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
                                    # update record yang sudah ada
                                    internal_ids.append((1, existing.id, d, external_odoo_id))
                                    continue
                            # buat record baru & link
                            internal_ids.append((0, 0, d, external_odoo_id))
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
        if self.state == 'done':
            if self.field_type == 'many2one' and self.related_external_data_sync_id:
                return self.related_external_data_sync_id.internal_odoo_id or None
            if self.internal_data_eval:
                return ast.literal_eval(self.internal_data_eval) or None

        return None

    def get_or_create(
            self, related_external_data_sync_id, external_data_sync_id, field_name,
            field_type='many2one', required_before_create=False, related_sync_strategy_id=False
    ):
        # value for this related related_external_data_sync_id
        # parent external_data_sync_id
        domain = [
            ('external_data_sync_id', '=', int(external_data_sync_id)),
            ('name', '=', field_name),
            ('field_type', '=', field_type),
        ]
        related = int(related_external_data_sync_id)
        existing = self.search(domain + [('related_external_data_sync_id', '=', related)], limit=1)
        if existing:
            return existing

        existing = self.search(domain + [('related_external_data_sync_id', '=', False)], limit=1)
        if existing:
            existing.write({
                'related_external_data_sync_id': related
            })
            return existing
        create_dict = {
            'name': field_name,
            'field_after_create': True,
            'internal_model': related_external_data_sync_id.internal_model,
            'external_data_sync_id': int(external_data_sync_id),
            'related_external_data_sync_id': related,
            'field_type': field_type,
            'required_before_create': required_before_create,
        }

        return self.create([create_dict])[0]

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
