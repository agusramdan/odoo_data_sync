# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json
from datetime import datetime, date
from odoo.tools.safe_eval import safe_eval, test_python_expr


class ExternalDataMappingInternal(models.Model):
    _name = 'external.data.lookup'
    _description = 'Lookup display_name to internal data object'
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If unchecked, it will allow you to hide the record without removing it."
    )
    name = fields.Char(
        help="display_name from external system for lookup"
    )
    external_model = fields.Char()
    external_app_name = fields.Char()
    internal_model = fields.Char()
    internal_id = fields.Integer()

    def action_open_internal(self):
        self.ensure_one()
        return {
            'name': _('Data Internal Data'),
            'type': 'ir.actions.act_window',
            'res_model': self.internal_model,
            'res_id': self.internal_id,
            'view_mode': 'form',
        }
