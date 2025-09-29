# -*- coding: utf-8 -*-

import requests
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import traceback
import logging

_logger = logging.getLogger(__name__)


# class JSONEncoder(json.JSONEncoder):
#     def default(self, obj):
#         if isinstance(obj, (datetime.date, datetime.datetime)):
#             return obj.isoformat()
#         if isinstance(obj, (bytes, bytearray)):
#             return obj.decode("utf-8")
#         return json.JSONEncoder.default(self, obj)


class ExternalServerSync(models.Model):
    _name = 'external.server.sync'

    active = fields.Boolean(default=True)
    name = fields.Char()
    app_name = fields.Char("Application Name")

    odoo_server_db = fields.Char()
    odoo_server_uid = fields.Integer(readonly=True)

    base_url = fields.Char()
    path = fields.Char(default='/api')
    auth_type = fields.Selection([
        ('basic', 'Basic'),
        ('token', 'Key Token'),
    ], default='basic')

    basic_auth_username = fields.Char()
    basic_auth_password = fields.Char()

    token_in = fields.Selection([(
        'header', 'Header'), ('param', 'Parameter'), ('body', 'Body')
    ], default='header')
    token_key = fields.Char(
        default='access_token'
    )
    token_value = fields.Char()

    # user_id = fields.Many2one('res.users')
    def get_endpoint_url(self):
        return f"{self.base_url}{self.path}"

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
        url = f"{self.base_url}/api/sync/authenticate"
        response = requests.post(url, data={
            'login': self.basic_auth_username,
            'password': self.basic_auth_password,
        })
        response.raise_for_status()
        json_data = response.json()
        self.odoo_server_db = json_data.get('db')
        self.odoo_server_uid = json_data.get('uid')

    def action_get_db_name(self):
        self.get_db_name()

    def jsonrpc_authenticate(self):
        if not self.odoo_server_db:
            self.get_db_name()

        if self.odoo_server_db:
            url = self.base_url + "/jsonrpc"
            db = self.odoo_server_db
            username = self.basic_auth_username
            password = self.basic_auth_password

            # 1. Authenticate
            auth_payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "common",
                    "method": "authenticate",
                    "args": [db, username, password, {}]
                },
                "id": 1,
            }
            res = requests.post(url, json=auth_payload).json()
            self.odoo_server_uid = res.get("result")

    def jsonrpc_call(self, model, method, args, kw=None):
        if self.odoo_server_db:
            if not self.odoo_server_uid:
                self.jsonrpc_authenticate()
            url = self.base_url + "/jsonrpc"
            db = self.odoo_server_db
            password = self.basic_auth_password
            args = [
                db,
                self.odoo_server_uid,
                password,
                model,
                method,
                args,
                kw
            ]
            obj_payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": args,
                },
                "id": 2,
            }
            try:
                response = requests.post(url, json=obj_payload)
                response.raise_for_status()
                json_data = response.json()
                if "error" in json_data:
                    raise Exception(f"Odoo Error: {json_data['error']}")
                return json_data.get("result")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Network Error: {str(e)}")
            except Exception as e:
                raise Exception(f"Unexpected Error: {str(e)}")
        else:
            raise UserError(_("Odoo server not configured"))

    def get_external_data(self, model_name, domain=None, fields=None, offset=None, limit=None, count=False,
                          object_id=None, context=None):
        if self.auth_type == 'basic' and self.odoo_server_db:
            if object_id and isinstance(object_id, int):
                method = 'read'
                args = [[object_id]]
                kw = {'fields': fields}
            elif count:
                method = 'search'
                args = [domain]
                kw = {'count': True}
            else:
                method = 'search_read'
                args = [domain]
                kw = {'fields': fields, 'offset': offset, 'limit': limit}

            if context:
                kw['context'] = context

            return self.jsonrpc_call(
                model_name,
                method,
                args,
                kw=kw
            )
        else:
            url = self.get_endpoint_model_name_url(model_name)
            headers = self.get_headers_request()
            params = {}
            if object_id and isinstance(object_id, int):
                url = f"{url}/{object_id}"
            else:
                if domain:
                    params['domain'] = str(domain)
                if fields is not None:
                    params['fields'] = str(fields)
                if offset is not None:
                    params['offset'] = offset
                if limit is not None:
                    params['limit'] = limit
                if count:
                    params['count'] = True
                if context:
                    params['context'] = str(context)
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            if count:
                return response.json().get("count", 0)
            return response.json().get("results", [])

#         if self.odoo_server_db:
#             if not self.odoo_server_uid:
#                 self.server_authenticate()
#             url = self.base_url + "/jsonrpc"
#             db = self.odoo_server_db
#             password = self.basic_auth_password
#             args = [
#                 db,
#                 self.odoo_server_uid,
#                 password,
#                 model_name,
#             ]
#             if object_id and isinstance(object_id, int):
#                 args.extend(['read', [object_id]])
#             elif count:
#                 args.extend(['search', [domain or []], {'count': True}])
#             else:
#                 args.extend(['search_read', [domain or []], {'fields': fields, 'offset': offset, 'limit': limit}])
#
#             obj_payload = {
#                 "jsonrpc": "2.0",
#                 "method": "call",
#                 "params": {
#                     "service": "object",
#                     "method": "execute_kw",
#                     "args": args,
#                 },
#                 "id": 2,
#             }
#             res = requests.post(url, json=obj_payload).json()
#
#             return res.get("result")
#
#         return None
# #
#
# class ExternalDataSyncModel(models.Model):
#     _name = 'external.data.sync.model'
#     _description = """
#     Model untuk menyimpan infomasi object yang bisa di sync dari aplikasi yang lain
#     """
#     _order = 'next_sync_datetime , last_sync_datetime'
#     active = fields.Boolean(default=True)
#     name = fields.Char(
#         string='Name', required=True,
#         help="Name internal model data sync configuration."
#     )
#     external_model = fields.Char()
#     external_app_name = fields.Char()
#     external_domain = fields.Text()
#     user_id = fields.Many2one('res.users')
#     next_sync_datetime = fields.Datetime()
#     last_sync_datetime = fields.Datetime()
#
#     def get_server_sync(self):
#         return self.env['external.server.sync'].sudo().search([('name', '=', self.external_app_name)], limit=1)
#
#     def action_sync_now(self):
#         return self.sync_from_application_server()
#
#     @api.model
#     def sync_from_application_server(self):
#         self.ensure_one()
#         server_sync = self.get_server_sync()
#         url = server_sync.get_endpoint_model_name_url(self.external_model)
#         headers = server_sync.get_headers_request()
#         params = {
#             'domain': self.external_domain or '[]',
#             'order': 'id asc'
#         }
#         offset = 0
#         total = 1
#         row_count = limit = 100
#         self.write({
#             'last_sync_datetime': fields.Datetime.now(),
#         })
#         while row_count == limit:
#             params['offset'] = offset
#             response = requests.get(url, params=params, headers=headers)
#             # ambil last sync datetime
#             # todo ambil data last sinc dari config param
#             if response.status_code == 404:
#                 break
#
#             if response.status_code != 200:
#                 raise UserError(f"Failed to fetch data: {response.status_code} - {response.text}")
#
#             json_data = response.json()
#             data = json_data.get("results", [])
#             row_count = json_data.get('count', 0)
#             _logger.info("Count %s ,Offset %s = Total %s", len(data), offset, row_count)
#             for item in data:
#                 offset = offset + 1
#                 self.env['external.data.sync'].sync_data_from_external(
#                     item, self.external_model, server_sync.name, self.name,
#                 )
#
#         _logger.info("Offset %s = total %s", offset, total)
#         self.write({
#             'next_sync_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
#         })
#
#     def cron_sync_from_server(self):
#         limit_time = fields.Datetime.now() + datetime.timedelta(minutes=10)
#         data_sync_models = self.search([
#             ('active', '=', True),
#             '|',
#             ('next_sync_datetime', '<=', fields.Datetime.now()),
#             ('next_sync_datetime', '=', False),
#         ])
#         for data_sync in data_sync_models:
#             try:
#                 data_sync.sync_from_application_server()
#             except Exception as e:
#                 _logger.error("Error sync from server %s , model %s : %s", data_sync.external_app_name,
#                               data_sync.external_model, traceback.format_exc())
#             if fields.Datetime.now() > limit_time:
#                 break
