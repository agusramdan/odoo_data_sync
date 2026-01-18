# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.addons.amr_jsonrpc import jsonrpc
import requests
import logging

_logger = logging.getLogger(__name__)


class ExternalServerSync(models.Model):
    _name = 'external.server.sync'
    _description = 'External Server Sync Configuration'

    active = fields.Boolean(default=True)
    name = fields.Char()
    app_name = fields.Char("Application Name")

    odoo_server_db = fields.Char()
    odoo_server_uid = fields.Integer()

    base_url = fields.Char()
    path = fields.Char(default='/api')
    auth_type = fields.Selection([
        ('jsonrpc', 'Json-RPC'),
        ('basic', 'Basic'),
        ('token', 'Key Token'),
    ], default='jsonrpc')

    basic_auth_username = fields.Char()
    basic_auth_password = fields.Char()

    token_in = fields.Selection([
        ('basic', 'Basic'),
        ('header', 'Header'),
        ('param', 'Parameter'),
        ('body', 'Body')
    ], default='header')
    token_key = fields.Char(
        default='token'
    )
    token_value = fields.Char()

    def get_auth_config(self):
        auth_type = self.auth_type
        token_key = self.token_key
        access_token = self.token_value
        if auth_type == 'token':
            auth_type = self.token_in
        db, uid, username, password = self.get_db_uid_username_password()
        return {
            'db': db,
            'uid': uid,
            'username': username,
            'password': password,
            'auth_mode': auth_type,
            'token_key': token_key,
            'access_token': access_token,
            'token_endpoint_url': None,
            'db_name_endpoint_url': self.get_db_name_endpoint_url()
        }

    def get_application_name(self):
        return self.app_name

    def get_endpoint_url(self):
        return f"{self.base_url}{self.path}"

    def get_db_name_endpoint_url(self):
        return f"{self.base_url}/sync/db_name"

    def get_endpoint_model_name_url(self, model_name):
        return f"{self.get_endpoint_url()}/{model_name}"

    def get_headers_request(self):
        return {
            self.token_key: self.token_value,
            "Accept": "application/json"
        }

    def get_model_name_data(self, model_name, ref_id):
        url = self.get_endpoint_model_name_url(model_name) + f"/{ref_id}"
        headers = self.get_headers_request()
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise UserError(f"Failed to fetch data: {response.status_code} - {response.text}")

        return response.json()[0]

    def get_db_name(self):
        return self.odoo_server_db

    def get_odoo_uid(self):
        return self.odoo_server_uid

    def get_username(self):
        return self.basic_auth_username

    def get_password(self):
        return self.basic_auth_password

    def get_db_uid_username_password(self):
        return self.get_db_name(), self.get_odoo_uid(), self.get_username(), self.get_password()

    def get_db_username_password(self):
        return self.get_db_name(), self.get_username(), self.get_password()

    def get_db_name_uid_password(self):
        odoo_server_db = self.get_db_name()
        odoo_server_uid = self.get_odoo_uid()
        if odoo_server_db and odoo_server_uid:
            return odoo_server_db, odoo_server_uid, self.basic_auth_password
        return self.sync_authenticate()

    def sync_authenticate(self):
        url = f"{self.base_url}/api/sync/authenticate"
        response = requests.post(url, data={
            'login': self.basic_auth_username,
            'password': self.basic_auth_password,
        })
        response.raise_for_status()
        json_data = response.json()
        odoo_server_db = json_data.get('db')
        odoo_server_uid = json_data.get('uid')
        return odoo_server_db, odoo_server_uid, self.basic_auth_password

    def action_get_db_name(self):
        self.get_db_name()

    def action_authenticate(self):
        try:
            if self.odoo_server_db:
                self.jsonrpc_authenticate()
            else:
                self.sync_authenticate()
        except Exception as e:
            _logger.error("Authentication failed: %s", str(e))
            raise UserError(_("Authentication failed: %s") % str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sukses',
                'message': 'Auntentikasi berhasil.',
                'type': 'success',  # bisa: success / warning / danger / info
                'sticky': False,  # True = tidak hilang otomatis
            }
        }

    def jsonrpc_path(self):
        return "/jsonrpc"

    def jsonrpc_endpoint_url(self):
        return self.get_base_url() + self.jsonrpc_path()

    def jsonrpc_authenticate(self):
        db, username, password = self.get_db_username_password()
        url = self.jsonrpc_endpoint_url()
        return jsonrpc.authenticate(url, db, username, password)

    # def jsonrpc_call(self, model, method, args, kw=None, db=None, uid=None, password=None):
    #     if db is None or uid is None or password is None:
    #         db, uid, password = self.get_db_name_uid_password()
    #
    #     url = self.jsonrpc_endpoint_url()
    #     return jsonrpc.execute_kw(url, model, method, args, kw=kw, db=db, uid=uid, password=password)
