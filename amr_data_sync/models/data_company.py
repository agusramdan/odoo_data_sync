# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

from odoo.addons.amr_data_sync.tools.utils import convert_from_external_data

_logger = logging.getLogger(__name__)


class ExternalDataLookup(models.Model):
    _name = 'external.data.company'
    _description = 'Configuration Lookup by display_name to internal data object'

    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    company_id = fields.Many2one('res.company')
    server_sync_id = fields.Many2one('external.server.sync', ondelete='set null')
    external_app_name = fields.Char(
        compute='_compute_external_app_name',
        inverse='_inverse_external_app_name',
        store=True
    )
    external_id = fields.Integer()
    external_model = fields.Char(default='res.company')

    # ===== COMPUTE =====
    @api.depends('server_sync_id', 'server_sync_id.app_name')
    def _compute_external_app_name(self):
        for rec in self:
            if rec.server_sync_id:
                rec.external_app_name = rec.server_sync_id.app_name
            # kalau server_sync_id kosong → JANGAN override
            # biarkan nilai manual tetap

    # ===== INVERSE =====
    def _inverse_external_app_name(self):
        for rec in self:
            # inverse wajib ada supaya field editable
            pass

    def lookup_company(self, external_data, server_sync=None,external_app_name=None):
        if not external_data:
            return None
        data_dict = convert_from_external_data(external_data)
        external_id = data_dict.get('id')
        if not external_id:
            return None
        if server_sync:
            result = self.search(
                [('external_id', '=', external_id), ('external_app_name', '=', external_app_name)], limit=1
            )
            if result:
                return result.company_id
            external_app_name = server_sync.get_application_name()
        result = self.search([('external_id','=',external_id),('external_app_name','=',external_app_name)],limit=1)
        return result.company_id


    def reverse_mapping(
            self, internal,
            server_sync=None,
            external_app_name=None,
            external_model=None,
            raise_not_found_exception=True
    ):
        if not internal:
            return [0], [0]

        if not isinstance(internal, models.BaseModel):
            _logger.error("Internal Object must")
            if raise_not_found_exception:
                raise ValueError("Internal Object must")
            return [0], [0]
        result_map = {}
        not_mapped_ids = set(internal.ids)

        def filter_by_domain(domain):
            rows = self.search(domain)
            mapping = defaultdict(list)
            for r in rows:
                mapping[r.company_id.id].append(r.external_id)
            return dict(mapping)

        if server_sync:
            external_app_name = server_sync.get_application_name()
            domain = [('company_id', 'in', list(not_mapped_ids)), ('server_sync_id', '=', server_sync.id)]
            r_map = filter_by_domain(domain)
            result_map.update(r_map)
            not_mapped_ids -= r_map.keys()

        if not external_app_name:
            _logger.error("external_app_name not set")
            if raise_not_found_exception:
                raise ValueError("external_app_name not set")
            return result_map, not_mapped_ids
        if external_model:
            domain = [('company_id', 'in', list(not_mapped_ids)),
                      ('external_app_name', '=', external_app_name), ('external_model', '=', external_model), ]
            r_map = filter_by_domain(domain)
            result_map.update(r_map)
            not_mapped_ids -= r_map.keys()
        else:
            domain = [('company_id', 'in', list(not_mapped_ids)),
                      ('external_app_name', '=', external_app_name), ('external_model', '=', 'res.company'), ]
            r_map = filter_by_domain(domain)
            result_map.update(r_map)
            not_mapped_ids -= r_map.keys()

        return result_map, not_mapped_ids
