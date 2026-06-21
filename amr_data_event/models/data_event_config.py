# -*- coding: utf-8 -*-

from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class InternalDataEventConfig(models.Model):
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
    filter_expr = fields.Char("Filter Expression")
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

    def action_snapshot(self):
        changed = self.get_fields_include()
        records = self.env[self.model_id.model].search([])
        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in records:
            data = {
                'name': rec.display_name,
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'snapshot',
                'changed_fields': ",".join(changed),
            }
            if 'company_id' in rec._fields and rec.company_id:
                data['company_id'] = rec.company_id.id
            event = AuditEvent.create(data)
            event.send_events()
