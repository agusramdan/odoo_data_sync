# -*- coding: utf-8 -*-

from odoo import api, fields, models, modules, _


class IrModel(models.Model):
    _inherit = 'ir.model'

    is_sync_data_api = fields.Boolean(
        'REST Sync Data API', default=False, help="Enable REST Sync/Read Data API for this object/model")

    is_create_data_api = fields.Boolean(
        'REST Create Data API', default=False, help="Enable REST Sync/Create Data API for this object/model")

    is_write_data_api = fields.Boolean(
        'REST Write Data API', default=False, help="Enable REST Sync/Write Data API for this object/model")

    is_unlink_data_api = fields.Boolean(
        'REST Write Data API', default=False, help="Enable REST Sync/Unlink Data API for this object/model")
