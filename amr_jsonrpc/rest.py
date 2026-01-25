import base64

import jwt
import time
from odoo.exceptions import UserError
from odoo import _
import requests
import logging

_logger = logging.getLogger(__name__)

import json
import base64
from odoo.fields import Datetime, Date
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class OdooJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return base64.b64encode(obj).decode()
        if isinstance(obj, datetime):
            return Datetime.to_string(obj)
        if isinstance(obj, date):
            return Date.to_string(obj)

        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


class OdooRestClient:

    def __init__(self, base_url: str):
        self.base_url = base_url and base_url.rstrip('/') or ""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

    def post(self, path, json=None, params=None, headers=None):
        url = f"{self.base_url}{path}"
        return self.session.post(
            url,
            json=json,
            params=params,
            headers=headers
        )

    def get(self, path, params=None, headers=None):
        url = f"{self.base_url}{path}"
        return self.session.get(
            url,
            params=params,
            headers=headers
        )


class OdooSessionAuth:

    def __init__(self, client):
        self.client = client

    def login(self, db: str, login: str, password: str):
        payload = {
            "jsonrpc": "2.0",
            "params": {
                "db": db,
                "login": login,
                "password": password
            }
        }

        resp = self.client.post(
            "/web/session/authenticate",
            json=payload
        )
        resp.raise_for_status()

        # session_id otomatis tersimpan di session.cookies
        return resp.json()


from requests.auth import HTTPBasicAuth


class BasicAuth:
    def apply(self, client: OdooRestClient, username, password):
        client.session.auth = HTTPBasicAuth(username, password)


class BearerAuth:
    def apply(self, client: OdooRestClient, token: str):
        client.session.headers.update({
            "Authorization": f"Bearer {token}"
        })


class HeaderTokenAuth:
    def apply(self, client: OdooRestClient, header_name, token):
        client.session.headers.update({
            header_name: token
        })


class ParamTokenAuth:
    def with_token(self, params: dict, param_name: str, token: str):
        params = params or {}
        params[param_name] = token
        return params


def basic_auth_header(username, password, headers=None):
    if headers is None:
        headers = {}
    token = f"{username}:{password}"
    encoded = base64.b64encode(token.encode()).decode()
    headers['Authorization'] = f"Basic {encoded}"
    return headers


def bearer_auth_header(access_token, headers=None):
    if headers is None:
        headers = {}
    headers['Authorization'] = f'Bearer {access_token}'
    return headers


def request_token(token_endpoint_url, login, password, client_id=None, client_secret=None, **kwargs):
    data = {'grant_type': 'password', 'username': login, 'password': password}
    headers = {}
    if client_id or client_secret:
        headers = basic_auth_header(client_id, client_secret)
    response = requests.post(token_endpoint_url, data=data, headers=headers)
    response.raise_for_status()
    json_result = response.json()
    rest_token = json_result.get('access_token')
    rest_refresh = json_result.get('refresh_token')
    return rest_token, rest_refresh


def request_refresh_token(token_endpoint_url, refresh_token, client_id=None, client_secret=None, **kwargs):
    data = {'grant_type': 'refresh_token', 'refresh_token': refresh_token}
    headers = {}
    if client_id or client_secret:
        headers = basic_auth_header(client_id, client_secret)
    response = requests.post(token_endpoint_url, data=data, headers=headers)
    response.raise_for_status()
    json_result = response.json()
    rest_token = json_result.get('access_token')
    rest_refresh = json_result.get('refresh_token')
    return rest_token, rest_refresh


class ModelObject(object):
    def __init__(self, model_name, **kwargs):

        self.model_name = model_name

        self.endpoint_url = kwargs.get('endpoint_url')
        self.token_endpoint_url = kwargs.get('token_endpoint_url')

        self.db = kwargs.get('db')
        self.uid = kwargs.get('uid')

        self.auth_model = kwargs.get('auth_model')

        # base
        self.username = kwargs.get('username')
        self.password = kwargs.get('password')

        self.token_key = kwargs.get('token_key', 'access_token')
        self.access_token = kwargs.get('access_token')
        self.refresh_token = kwargs.get('refresh_token')

        self.context = kwargs.get('context', {})
        self.domain = kwargs.get('domain', [])
        self.fields = kwargs.get('fields')
        self.offset = kwargs.get('offset', 0)
        self.limit = kwargs.get('limit', 500)
        self.order = kwargs.get('order', None)

        ids = kwargs.get('ids', [])
        if ids and isinstance(ids, int):
            self.ids = [ids]
        else:
            self.ids = ids or []

    def clone(self, **overrides):
        data = {
            'endpoint_url': self.endpoint_url,
            'token_endpoint_url': self.token_endpoint_url,
            'auth_model': self.auth_model,
            'db': self.db,
            'uid': self.uid,
            'username': self.username,
            'password': self.password,
            'context': dict(self.context),
            'domain': list(self.domain),
            'fields': self.fields,
            'offset': self.offset,
            'limit': self.limit,
            'order': self.order,
            'ids': list(self.ids),
        }
        data.update(overrides)
        return ModelObject(self.model_name, **data)

    # def __getattr__(self, method):
    #     def delegate_func(*args, **kw):
    #         args = list(args)
    #         if self.ids is not None:
    #             args = [self.ids] + args
    #         url, db, uid, password = self.get_url_db_uid_password()
    #         return execute_kw(
    #             url, self.model_name, method, args=args, kw=kw, db=db, uid=uid, password=password
    #         )
    #
    #     return delegate_func

    def browse(self, ids):
        if ids and isinstance(ids, int):
            ids = [ids]
        else:
            ids = ids or []
        return self.copy_model(
            ids=ids
        )

    def copy_model(self, **kwargs):
        return ModelObject(self.model_name, **kwargs)

    def get_db(self):
        return self.db

    def get_username(self):
        return self.username

    def get_password(self):
        return self.password

    def get_endpoint_url(self):
        return self.endpoint_url

    def get_token_endpoint_url(self):
        return self.token_endpoint_url

    def get_url_db_username_password(self):
        return self.get_endpoint_url(), self.get_db(), self.get_username(), self.get_password()

    def get_endpoint_model_name_url(self):
        return f"{self.get_endpoint_url()}/{self.model_name}"

    def rest_headers(self, headers=None):
        if self.auth_model == 'basic':
            return self.rest_basic_header(headers)
        if self.auth_model == 'bearer':
            return self.rest_bearer_header(headers)
        if self.auth_model == 'header':
            if headers is None:
                headers = {}
            headers[self.token_key] = self.ensure_token()
        return headers

    def rest_bearer_header(self, headers=None):
        return bearer_auth_header(self.ensure_token(), headers)

    def rest_basic_header(self, headers=None):
        username, password = self.get_username_password()
        return basic_auth_header(username, password, headers)

    def ensure_token(self, force=False):
        if force or self.is_token_expired():
            self.rest_post_refresh()

    def rest_post_refresh(self, **kwargs):
        rest_token, rest_refresh = request_refresh_token(self.get_token_endpoint_url(), self.refresh_token, **kwargs)
        if rest_token:
            self.access_token = rest_token
        if rest_refresh:
            self.refresh_token = rest_refresh
        return rest_token

    def is_token_expired(self):
        try:
            payload = jwt.decode(
                self.access_token,
                options={"verify_signature": False}
            )
        except Exception:
            return False

        exp = payload.get("exp")
        if not exp:
            return True  # tidak ada exp → anggap expired

        now = int(time.time())
        return now >= exp

    def get_username_password(self):
        return self.username, self.password

    def get_headers_request(self):
        return self.rest_headers({"Accept": "application/json"})

    def ensure_authenticate(self):
        return self

    def retry_authenticate(self):
        pass

    def rest_get(self, params=None, object_id=None):
        url = self.get_endpoint_model_name_url()
        if object_id and isinstance(object_id, int):
            url = f"{url}/{object_id}"

        self.ensure_authenticate()
        headers = self.get_headers_request()
        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 401:
            self.retry_authenticate()
            headers = self.get_headers_request()
            response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response

    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        params = {}

        domain = domain or self.domain
        if domain:
            params['domain'] = str(domain)

        fields = fields or self.fields
        if fields is not None:
            params['fields'] = str(fields)

        offset = offset or self.offset
        if offset is not None:
            params['offset'] = offset

        order = order or self.order
        if offset is not None:
            params['order'] = order

        limit = limit or self.limit
        if limit is not None:
            params['limit'] = limit

        if self.context:
            params['context'] = str(self.context)

        response = self.rest_get(params=params)
        return response.json().get("results", [])

    def read(self, fields=None, _id=None):
        if not _id and self.ids and isinstance(self.ids, (list, tuple)):
            _id = self.ids[0]
        if not _id:
            raise Exception("No _id can not call read")
        params = {}
        fields = fields or self.fields
        if fields is not None:
            params['fields'] = str(fields)
        if self.context:
            params['context'] = str(self.context)

        response = self.rest_get(params=params, object_id=_id)
        return response.json().get("results", [])

    def search_count(self):
        params = {}
        if self.domain:
            params['domain'] = str(self.domain)
        if self.context:
            params['context'] = str(self.context)
        params['count'] = True
        response = self.rest_get(params=params)
        return response.json().get("count", 0)

    def external_data_callback(self, call_back):
        total = self.search_count()
        offset = 0
        row_count = self.limit
        limit = self.limit
        _logger.info("Start : external_data_callback %s = total %s", self.model_name, total)
        while total and row_count == limit:
            data = self.search_read(offset=offset, limit=limit)
            row_count = len(data) if data else 0
            if row_count == 0:
                break
            _logger.info("Count %s ,Offset %s, Total: %s", row_count, offset, total)
            for item in data:
                offset = offset + 1
                self.ids = [item.get('id')]
                call_back(item, offset=offset, total=total)

        _logger.info("Done : Offset %s = total %s", offset, total)

    def __str__(self):
        return "rest.ModelObject({})".format(self.model_name)

    __repr__ = __str__


def model_object(model, **kwargs):
    obj = ModelObject(model, **kwargs)
    return obj.ensure_authenticate()
