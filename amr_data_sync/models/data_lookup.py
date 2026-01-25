# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError


class ExternalDataLookup(models.Model):
    _name = 'external.data.lookup'
    _description = 'Configuration Lookup by display_name to internal data object'
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    name = fields.Char(
        help="display_name from external system for lookup"
    )
    external_model = fields.Char()
    external_id = fields.Integer()
    external_app_name = fields.Char(
        help="""set '*' bila ingin berlaku untuk semua application"""
    )
    internal_model = fields.Char()
    internal_id = fields.Integer()
    reverse_able = fields.Boolean()

    def action_open_internal(self):
        self.ensure_one()
        if self.internal_model and self.internal_id:
            return {
                'name': _('Lookup Data'),
                'type': 'ir.actions.act_window',
                'res_model': self.internal_model,
                'res_id': self.internal_id,
                'view_mode': 'form',
            }
        else:
            raise UserError("Data Not Ready. Please Sync First.")

    def get_internal_object(self):
        return self and self.internal_id and self.env[self.internal_model].browse(self.internal_id)

    def lookup_internal(self, external_app_name, external_model, internal_model, external_id=None, display_name=None):

        if not external_app_name or not external_model or not internal_model:
            raise UserError("Invalid parameter")

        def lookup(domain):
            data_lookup = None
            if external_id and display_name:
                data_lookup = self.search(domain + [
                    ('external_id', '=', external_id),
                    ('name', '=', display_name),
                ], limit=1).get_internal_object()

            if external_id and not data_lookup:
                data_lookup = self.search(domain + [
                    ('external_id', '=', external_id),
                ], limit=1).get_internal_object()

            if display_name and not data_lookup:
                data_lookup = self.search(domain + [
                    ('name', '=', display_name),
                ], limit=1).get_internal_object()
            return data_lookup

        return lookup([
            ('external_app_name', '=', external_app_name),
            ('external_model', '=', external_model),
            ('internal_model', '=', internal_model),
        ]) or lookup([
            ('external_app_name', '=', '*'),
            ('external_model', '=', external_model),
            ('internal_model', '=', internal_model),
        ])
