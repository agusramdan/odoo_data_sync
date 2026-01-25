# -*- coding: utf-8 -*-

from odoo import models, fields, _
import logging

_logger = logging.getLogger(__name__)


class ApplicationPath(models.Model):
    _name = 'application.path'

    active = fields.Boolean(default=True)
    name = fields.Char()
    application_auth_id = fields.Many2one(
        'application.auth', domain=[('auth_type', '=', 'rest-token')]
    )
    application_resource_id = fields.Many2one(
        'application.resource', store=True, readonly=True,
        related='application_auth_id.application_resource_id',
    )
    path = fields.Char()

    def get_path(self):
        return self.path

    def get_rest_path_client(self):
        return self.application_auth_id.get_rest_path_client(self.get_path())

    def action_open_view(self):
        self.ensure_one()
        return {
            'name': _('Server Path'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
        }
