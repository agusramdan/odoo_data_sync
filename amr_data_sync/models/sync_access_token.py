# -*- coding: utf-8 -*-
# Author: Ivan Yelizariev, Ildar
# Ref. from: https://github.com/it-projects-llc/odoo-saas-tools/blob/10.0/oauth_provider/models/oauth_provider.py

import logging

from odoo import models, fields, api
from datetime import datetime, timedelta

from odoo.exceptions import AccessDenied
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

_logger = logging.getLogger(__name__)

try:
    from oauthlib import common as oauthlib_common
except ImportError:
    _logger.warning(
        'OAuth library not found. If you plan to use it, '
        'please install the oauth library from '
        'https://pypi.python.org/pypi/oauthlib')


class SyncAccessToken(models.Model):
    _name = 'sync.access_token'
    active = fields.Boolean(default=True)
    token = fields.Char('Access Token', required=True)
    user_id = fields.Many2one('res.users', string='User')
    expires = fields.Datetime('Expires')

    def _get_access_token(self, user_id=None, create=False):
        if not user_id:
            user_id = self.env.user.id

        access_token = self.env['sync.access_token'].sudo().search(
            [('user_id', '=', user_id)], order='id DESC', limit=1)
        if access_token:
            access_token = access_token[0]
            # if access_token.is_expired():
            #     access_token = None
        if not access_token and create:
            vals = {
                'user_id': user_id,
                'token': oauthlib_common.generate_token(),
            }
            value = int(self.env['ir.config_parameter'].sudo().get_param('amr_data_sync.access_token_expires_in'))
            if value:
                expires = datetime.now() + timedelta(seconds=value)
                vals['expires'] = expires.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            access_token = self.sudo().create(vals)
            # we have to commit now
            # be called before we finish current transaction.
            self._cr.commit()
        if not access_token:
            return None
        return access_token.token

    def is_expired(self):
        self.ensure_one()
        if not self.expires:
            return False
        return datetime.now() > fields.Datetime.from_string(self.expires)


class ResUsers(models.Model):
    _inherit = 'res.users'

    sync_token_ids = fields.One2many(
        'sync.access_token', 'user_id', string="Access Tokens")

    def action_create_sync_token(self):
        self.sync_token_ids._get_access_token(user_id=self.id, create=True)

    def _check_credentials(self, password):
        try:
            return super(ResUsers, self)._check_credentials(password)
        except AccessDenied:
            res = self.sync_token_ids.sudo().search([('user_id', '=', self.env.uid), ('token', '=', password)])
            if not res:
                raise
