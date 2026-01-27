# -*- coding: utf-8 -*-

from requests import RequestException
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .. import remote
import logging
import requests
from contextlib import contextmanager
from datetime import datetime
import uuid

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

    def get_rest_url(self, path=None):
        base_path = self.get_path()
        base_url = self.get_endpoint_url()
        if path:
            if path != '/':
                path = base_path
            elif not path.startswith('/'):
                path = f"{base_path}/{path}"
        else:
            path = base_path

        if path:
            if path.startswith('/'):
                return f"{base_url}{path}"
            else:
                return f"{base_url}/{path}"
        return base_url

    @api.model
    def get_path(self):
        return ""

    @api.model
    def get_odoo_db_name_path(self):
        return '/sync/db_name'

    @api.model
    def get_endpoint_url(self):
        raise NotImplemented

    def get_db_name_endpoint_url(self):
        return f"{self.get_endpoint_url()}{self.get_odoo_db_name_path()}"

    @api.model
    def get_token_endpoint_url(self):
        return self.refresh_endpoint

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

    # def create_auth_client(
    #         self, endpoint_url=None, auth_type=None, **kwargs):
    #     auth_type = auth_type or self.get_auth_type()
    #     endpoint_url = endpoint_url or self.get_endpoint_url()
    #     if auth_type == 'odoo-rcp':
    #         db, uid, username, password = self.get_db_uid_username_password()
    #         session_auth = OdooSessionAuth(
    #             endpoint_url, db=db, login=username, password=password, uid=uid
    #         )
    #         session_auth.login_session()
    #     elif auth_type == 'jwt-odoo-rcp':
    #         db, uid, username, password = self.get_db_uid_username_password()
    #         session_auth = OdooSessionAuth(
    #             endpoint_url, db=db, login=username, password=password, uid=uid
    #         )
    #         session_auth.login_session()
    #     elif auth_type == 'jwt-rest-token':
    #         session_auth = TokenAuth(
    #             endpoint_url,
    #             self.access_token,
    #             refresh_token=self.refresh_token,
    #             refresh_endpoint=self.refresh_endpoint or self.get_token_endpoint_url(),
    #             expires_at=self.expires_at
    #         )
    #     elif auth_type in ['rest-token', 'token']:
    #         if self.token_in == 'basic':
    #             username, password = self.get_username_password()
    #             session_auth = BasicAuth(
    #                 endpoint_url, username=username, password=password, path=kwargs.get('path')
    #             )
    #         elif self.token_in == 'bearer':
    #             session_auth = TokenAuthBearer(
    #                 endpoint_url,
    #                 self.access_token,
    #                 path=kwargs.get('path'),
    #             )
    #
    #         elif self.token_in == 'header':
    #             session_auth = HeaderTokenAuth(
    #                 endpoint_url,
    #                 self.token_key,
    #                 self.access_token,
    #                 path=kwargs.get('path'),
    #             )
    #         elif self.token_in == 'param':
    #             session_auth = ParamTokenAuth(
    #                 endpoint_url,
    #                 self.token_key,
    #                 self.access_token,
    #                 path=kwargs.get('path'),
    #             )
    #         else:
    #             raise UserError("Invalid token_in")
    #     else:
    #         raise UserError("Invalid auth_type")
    #     return session_auth

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

    def create_session(self):
        """
        State Lest
        Contoh penggunaan
        auth = self.env.ref('test.auth')
        with auth.create_session() as s:
            r = s.get(f"{server.get_rest_url('/api/health')}")

        """
        return remote.OdooSession(self)

    @contextmanager
    def create_remote_model(self, model_name, **kwargs):
        """
        statefull
        Contoh penggunaan
        auth = self.env.ref('test.auth')
        with auth.create_remote_model('res.partner) as s:
            r = s.read([1])")
        """
        odoo_session = self.create_session()
        try:
            remote_model = odoo_session.create_remote_model(model_name, **kwargs)
            odoo_session.connect()
            yield remote_model
        finally:
            odoo_session.close()

    def connect_session(self, odoo_session):
        self._apply_auth(odoo_session)

    def reconnect_session(self, odoo_session):
        self._apply_auth(odoo_session)

    def _apply_odoo_rpc_auth(self, odoo_session):
        self.ensure_one()
        payload = {
            "jsonrpc": "2.0",
            "params": {
                "db": self.odoo_server_db,
                "login": self.username,
                "password": self.password
            }
        }
        resp = odoo_session.post(
            f"{self.get_endpoint_url()}/web/session/authenticate",
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        # JSON-RPC error
        if "error" in data:
            raise RuntimeError(f"Odoo login error: {data['error']}")

        result = data.get("result") or {}

        # uid False / None
        if not result.get("uid"):
            raise RuntimeError("Odoo login failed: invalid credentials")

        # valid session_id cookie
        if "session_id" not in odoo_session.cookies:
            raise RuntimeError("Odoo login failed: session_id not set")

        # simpan uid (cookie sudah otomatis di session)
        self.odoo_server_uid = result.get("uid")

    def _apply_auth(self, odoo_session: requests.Session):
        if self.auth_type in ('basic',):
            self._apply_basic_auth(odoo_session)
        elif self.auth_type in ('odoo-rcp',):
            self._apply_odoo_rpc_auth(odoo_session)
        elif self.auth_type in ('token', 'rest-token', 'jwt-rest-token'):
            self._apply_token_auth(odoo_session)
        else:
            raise ValueError(f"Unsupported auth_type: {self.auth_type}")

    def _apply_basic_auth(self, odoo_session):
        odoo_session.auth = (self.username, self.password)

    def _apply_token_auth(self, odoo_session):
        self._refresh_token_if_needed()

        token = self.access_token
        key = self.token_key or "token"

        if self.token_in == "bearer":
            odoo_session.headers["Authorization"] = f"Bearer {token}"

        elif self.token_in == "basic":
            odoo_session.headers["Authorization"] = f"Basic {token}"

        elif self.token_in == "header":
            odoo_session.headers[key] = token

        elif self.token_in == "param":
            odoo_session.params[key] = token

        elif self.token_in == "body":
            odoo_session.headers["X-Token-In-Body"] = key  # marker

    def _refresh_token_if_needed(self):
        refresh_endpoint = self.get_token_endpoint_url()
        if not refresh_endpoint:
            return

        if self.expires_at and fields.Datetime.now() < self.expires_at:
            return

        resp = requests.post(
            refresh_endpoint,
            data={
                "grant_type": 'refresh_token',
                "refresh_token": self.refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()

        data = resp.json()
        self.write({
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": datetime.utcnow() + fields.DateTime.timedelta(seconds=data.get("expires_in", 3600)),
        })

    def jsonrpc_execute_kw(self, model, method, args, kw=None):
        auth = self.ensure_one()
        with auth.create_session() as rpc:
            return rpc.jsonrpc_call(model, method, args, kw=kw)

    def jsonrpc_call(self, model, method, args, kw=None):
        auth = self.ensure_one()
        with auth.create_session() as rpc:
            return rpc.jsonrpc_call(model, method, args, kw=kw)

    def action_get_odoo_db_name(self):
        url = f"{self.get_endpoint_url()}/sync/db_name"
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

    def action_get_odoo_server_uid(self):
        odoo_session = self.create_session()
        try:
            odoo_session.connect()
            #     db, uid, password = self.jsonrpc_authenticate()
            #     if uid:
            #         self.write({'odoo_server_uid': uid})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': _("Get UID successful. (DB: %s, UID: %s)") % (self.odoo_server_db, self.odoo_server_uid),
                    'type': 'info',
                }
            }
        #     else:
        #         raise UserError(_("Authentication failed. Please check your credentials."))
        except Exception:
            raise UserError(_("Authentication failed. Please check your username or credentials."))
        finally:
            odoo_session.close()

    def action_test_connection(self):
        self.action_get_odoo_server_uid()
        # odoo_session = self.create_session()
        # odoo_session.connect()
        # try:
        #     db, uid, password = self.jsonrpc_authenticate()
        #     if not uid:
        #         raise UserError(_("Authentication failed. Please check your credentials."))
        #     return {
        #         'type': 'ir.actions.client',
        #         'tag': 'display_notification',
        #         'params': {
        #             'title': 'Info',
        #             'message': _("Connection successful. (DB: %s, UID: %s)") % (db, uid),
        #             'type': 'info',
        #         }
        #     }
        # except Exception as e:
        #     raise UserError(_("Connection failed: %s") % str(e))
