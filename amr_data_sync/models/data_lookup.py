# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
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

    server_sync_id = fields.Many2one('external.server.sync', ondelete='set null')
    external_app_name = fields.Char(
        compute='_compute_external_app_name',
        inverse='_inverse_external_app_name',
        store=True,
        help="""set '*' bila ingin berlaku untuk semua application"""
    )
    internal_ref = fields.Reference(
        selection='_selection_internal_model',
        string='Internal Reference',
    )
    internal_model = fields.Char(readonly=True)
    internal_id = fields.Integer(readonly=True)
    reverse_able = fields.Boolean()

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

    @api.model
    def _selection_internal_model(self):
        IrModel = self.env['ir.model'].sudo()

        domain = [
            ('transient', '=', False),
            #('abstract', '=', False),
            ('model', 'not ilike', 'ir.'),
            ('model', 'not ilike', 'base.'),
            ('model', 'not ilike', 'bus.'),
        ]

        # optional whitelist via context
        allowed = self.env.context.get('allowed_internal_models')
        if allowed:
            domain.append(('model', 'in', allowed))

        models = IrModel.search(domain)

        return [(m.model, m.name) for m in models]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ref = vals.get('internal_ref')
            if ref:
                model, res_id = ref.split(',')
                vals.update({
                    'internal_model': model,
                    'internal_id': int(res_id),
                })
        return super().create(vals_list)

    def write(self, vals):
        ref = vals.get('internal_ref')
        if ref:
            model, res_id = ref.split(',')
            vals.update({
                'internal_model': model,
                'internal_id': int(res_id),
            })
        return super().write(vals)

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
