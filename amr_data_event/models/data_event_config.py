# -*- coding: utf-8 -*-

from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class InternalDataSync(models.Model):
    _name = 'internal.data.event.config'
    _description = """
    """
    _rec_name = 'model_id'

    model_id = fields.Many2one(
        'ir.model',
        required=True,
        ondelete='cascade'
    )
    model_name = fields.Char(related='model_id.name')
    fields_include = fields.Char(
        help="Comma separated field names to include."
    )
    fields_exclude = fields.Char(
        help="Comma separated field names to exclude."
    )
    log_create = fields.Boolean(default=True)
    log_write = fields.Boolean(default=True)
    log_unlink = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    sudo_read = fields.Boolean(default=False)

    _sql_constraints = [
        ('uniq_model', 'unique(model_id)', 'Event config already exists')
    ]

    def get_fields_include(self):
        return (self and self.fields_include and [x.strip() for x in self.fields_include.split(',')]) or []

    def get_fields_exclude(self):
        return (self and self.fields_exclude and [x.strip() for x in self.fields_exclude.split(',')]) or []

    def is_event_sync(self, model_name):
        return self.search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
        ], limit=1) and True

    def is_sudo_read(self, model_name):
        return self.search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
        ], limit=1).sudo_read and True

    def get_config(self, model_name):
        return self.search([('model_id.model', '=', model_name)], limit=1)


    def get_config_create(self, model_name):
        return self.search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
            ('log_create', '=', True),
        ], limit=1)

    def get_config_write(self, model_name):
        return self.search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
            ('log_write', '=', True),
        ], limit=1)

    def get_config_unlink(self, model_name):
        return self.search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
            ('log_unlink', '=', True),
        ], limit=1)
