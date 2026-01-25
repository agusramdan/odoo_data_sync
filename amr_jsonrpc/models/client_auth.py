# -*- coding: utf-8 -*-

from requests import RequestException
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..client import OdooSessionAuth, TokenAuth, BasicAuth, TokenAuthBearer, HeaderTokenAuth, ParamTokenAuth
import requests
import logging

_logger = logging.getLogger(__name__)


class AuthRestToken(models.AbstractModel):
    _name = 'client.auth.mixin'

    auth_type = fields.Selection([
        ('odoo-rcp', 'Odoo RCP'),
        ('jwt-odoo-rcp', 'JWT Odoo RCP'),
        ('rest-token', 'Rest Token'),
        ('jwt-rest-token', 'JWT Rest Token'),
        ('basic', 'Basic'),
    ], default='rest-token')
    # rest-token
    token_in = fields.Selection([
        ('basic', 'Basic'),
        ('bearer', 'Bearer'),
        ('header', 'Header'),
        ('param', 'Parameter'),
        ('body', 'Body')
    ], default='header')
    token_key = fields.Char(
        default='token'
    )

    access_token = fields.Char()
    refresh_token = fields.Char()
    refresh_endpoint = fields.Char()
    expires_at = fields.Datetime()

    username = fields.Char()
    password = fields.Char()

    odoo_server_db = fields.Char()
    odoo_server_uid = fields.Integer()

    def get_path(self):
        raise NotImplemented

    @api.model
    def get_odoo_db_name_path(self):
        return '/sync/db_name'

    def get_endpoint_url(self):
        raise NotImplemented

    def get_db_name_endpoint_url(self):
        return f"{self.get_endpoint_url()}{self.get_odoo_db_name_path()}"

    def get_token_endpoint_url(self):
        raise NotImplemented

    def get_application_name(self):
        raise NotImplemented

    def get_auth_type(self):
        return self.auth_type

    def get_db_name(self):
        return self.odoo_server_db

    def get_odoo_uid(self):
        return self.odoo_server_uid

    def get_username(self):
        return self.username

    def get_password(self):
        return self.password

    def get_username_password(self):
        return self.get_username(), self.get_password()

    def get_db_username_password(self):
        return self.get_db_name(), self.get_username(), self.get_password()

    def get_db_uid_username_password(self):
        return self.get_db_name(), self.get_odoo_uid(), self.get_username(), self.get_password()

    def create_auth_client(
            self, endpoint_url=None, auth_type=None, **kwargs):
        auth_type = auth_type or self.get_auth_type()
        endpoint_url = endpoint_url or self.get_endpoint_url()
        if auth_type == 'odoo-rcp':
            db, uid, username, password = self.get_db_uid_username_password()
            session_auth = OdooSessionAuth(
                endpoint_url, db=db, login=username, password=password, uid=uid
            )
            session_auth.login_session()
        elif auth_type == 'jwt-odoo-rcp':
            db, uid, username, password = self.get_db_uid_username_password()
            session_auth = OdooSessionAuth(
                endpoint_url, db=db, login=username, password=password, uid=uid
            )
            session_auth.login_session()
        elif auth_type == 'jwt-rest-token':
            session_auth = TokenAuth(
                endpoint_url,
                self.access_token,
                refresh_token=self.refresh_token,
                refresh_endpoint=self.refresh_endpoint or self.get_token_endpoint_url(),
                expires_at=self.expires_at
            )
        elif auth_type in ['rest-token', 'token']:
            if self.token_in == 'basic':
                username, password = self.get_username_password()
                session_auth = BasicAuth(
                    endpoint_url, username=username, password=password, path=kwargs.get('path')
                )
            elif self.token_in == 'bearer':
                session_auth = TokenAuthBearer(
                    endpoint_url,
                    self.access_token,
                    path=kwargs.get('path'),
                )

            elif self.token_in == 'header':
                session_auth = HeaderTokenAuth(
                    endpoint_url,
                    self.token_key,
                    self.access_token,
                    path=kwargs.get('path'),
                )
            elif self.token_in == 'param':
                session_auth = ParamTokenAuth(
                    endpoint_url,
                    self.token_key,
                    self.access_token,
                    path=kwargs.get('path'),
                )
            else:
                raise UserError("Invalid token_in")
        else:
            raise UserError("Invalid auth_type")
        return session_auth

    def action_get_odoo_db_name(self):
        url = f"{self.rest_endpoint_url()}{self.get_odoo_db_name_path()}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            result = response.json()
            db = result.get('db')
            if not db:
                raise UserError('DB not found')
            self.odoo_server_db = db
        except RequestException as e:
            raise UserError(str(e))

    def action_open_token_wizard(self):
        context = dict(self.env.context)
        context['default_username'] = self.username
        context['default_url'] = self.get_token_endpoint_url()
        context['action_id'] = self.id
        context['action_model'] = self._name
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'amr.get.token.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context
        }
