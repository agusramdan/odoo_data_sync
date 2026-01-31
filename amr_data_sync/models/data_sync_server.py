# -*- coding: utf-8 -*-

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ExternalServerSync(models.Model):
    _name = 'external.server.sync'
    _inherit = 'client.auth.mixin'
    _description = 'External Server Sync Configuration'

    active = fields.Boolean(default=True)
    name = fields.Char()
    app_name = fields.Char("Application Name")

    odoo_server_db = fields.Char()
    odoo_server_uid = fields.Integer()

    base_url = fields.Char()
    path = fields.Char(default='/api')
    auth_type = fields.Selection([
        ('odoo-rcp', 'Odoo RCP'),
        ('jwt-odoo-rcp', 'JWT Odoo RCP'),
        ('rest-token', 'Rest Token'),
        ('jwt-rest-token', 'JWT Rest Token'),
        ('basic', 'Basic'),
        ('jsonrpc', 'Json-RPC-Deprecated'),
        ('token', 'Key Token-Deprecated'),
    ], default='odoo-rcp')

    basic_auth_username = fields.Char(related='username', store=True)
    basic_auth_password = fields.Char(related='password', store=True)

    token_in = fields.Selection([
        ('basic', 'Basic'),
        ('header', 'Header'),
        ('param', 'Parameter'),
        ('body', 'Body')
    ], default='header')
    token_key = fields.Char(default='token')
    token_value = fields.Char(related='access_token', store=True)

    def get_application_name(self):
        return self.app_name

    def get_endpoint_url(self):
        return self.base_url

    def get_path(self):
        return self.path
