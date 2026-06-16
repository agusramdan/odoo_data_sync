# -*- coding: utf-8 -*-

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ExternalServerSync(models.Model):
    _name = 'external.server.sync'
    _inherit = 'service.endpoint.mixin'
    _description = 'External Server Sync Configuration'

    active = fields.Boolean(default=True)
    name = fields.Char()
    app_name = fields.Char("Application Name")
    audience = fields.Char(related='app_name', store=True, readonly=False)

    def get_application_name(self):
        return self.app_name

    def get_endpoint_url(self):
        return self.base_url

    def create_remote_model(self, external_model, **kwargs):
        return self.env['service.client'].get_remote_object(self, external_model, **kwargs)
