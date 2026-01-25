# -*- coding: utf-8 -*-

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ApplicationAuth(models.Model):
    _name = 'application.auth'

    active = fields.Boolean(default=True)
    name = fields.Char()

    auth_type = fields.Selection([
        ('base', 'Base'),
        ('odoo-rcp', 'Odoo RCP'),
        ('rest-token', 'Rest Token'),
    ], default='odoo-rcp')
    application_resource_id = fields.Many2one('application.resource', )
    application_path_ids = fields.One2many('application.path', 'application_auth_id', )

    # base auth and odoo rcp
    username = fields.Char()
    password = fields.Char()

    # odoo rcp
    odoo_server_db = fields.Char("DB")
    odoo_server_uid = fields.Integer("UID")

    # rest-token, oauth2
    token_in = fields.Selection([
        ('bearer', 'Bearer'),
        ('header', 'Header'),
        ('param', 'Parameter'),
        ('body', 'Body')
    ], default='header')
    token_key = fields.Char(default='basic')
    access_token = fields.Char()
    refresh_token = fields.Char()

    def get_rest_client(self):
        raise NotImplemented

    def get_rest_path_client(self, path):
        raise NotImplemented

    def get_odoo_client(self):
        raise NotImplemented

    def get_odoo_remote(self, model_name):
        raise NotImplemented
