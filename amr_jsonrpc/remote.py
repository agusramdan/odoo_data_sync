from requests.auth import HTTPBasicAuth
from odoo.fields import Datetime, Date
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import requests
import base64
import logging

_logger = logging.getLogger(__name__)


def normalize_json(value):
    """
    Convert Python objects into JSON-serializable types (recursive)
    """
    if value is None:
        return None

    # Primitive JSON-safe
    if isinstance(value, (str, int, float, bool)):
        return value

    # datetime / date
    if isinstance(value, datetime):
        return Datetime.to_string(value)
    if isinstance(value, date):
        return Date.to_string(value)

    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode()

    if isinstance(value, UUID):
        return str(value)

    # Decimal → float (atau str kalau mau aman)
    if isinstance(value, Decimal):
        return float(value)

    # dict → recursive
    if isinstance(value, dict):
        return {
            k: normalize_json(v)
            for k, v in value.items()
        }

    # list / tuple / set → list
    if isinstance(value, (list, tuple, set)):
        return [normalize_json(v) for v in value]

    # fallback (object aneh)
    return str(value)


# =========================
# SAFE CALL (AUTO HANDLER)
# =========================
def safe_call(call_func, auth):
    if not auth:
        return call_func

    try:
        # proactive refresh
        if hasattr(auth, "is_expired") and auth.is_expired():
            auth.refresh()
        return call_func()

    except requests.HTTPError as e:
        if e.response.status_code == 401:
            # reactive relogin / refresh
            if hasattr(auth, "refresh"):
                auth.refresh()
            elif hasattr(auth, "login_session"):
                auth.login_session()
            return call_func()
        raise


def rest_url(base_url, base_path=None, path=None):
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


class RemoteModel:
    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        self.context = kwargs.get('context', {})
        self.domain = kwargs.get('domain', [])
        self.fields = kwargs.get('fields')
        self.offset = kwargs.get('offset', 0)
        self.limit = kwargs.get('limit', 500)
        self.order = kwargs.get('order', None)

    def call(self, method, args, kw=None):
        raise NotImplemented

    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        method = 'search_read'
        args = []
        kw = {
            'domain': domain or self.domain or [],
            'fields': fields or self.fields, 'order': order or self.order,
            'offset': offset or self.offset, 'limit': limit or self.limit,
        }
        return self.call(method, args, kw=kw)

    def read(self, *args, fields=None):
        method = 'read'
        # if not args and self.ids and isinstance(self.ids, (list, tuple)):
        #     args = self.ids
        kw = {'fields': fields or self.fields}
        return self.call(method, args, kw=kw)

    def search_count(self):
        method = 'search_count'
        args = [self.domain or []]
        return self.call(method, args=args)

    def external_data_callback(self, call_back):
        total = self.search_count()
        offset = 0
        limit = self.limit
        row_count = self.limit
        _logger.info("Start : external_data_callback %s = total %s", self.model_name, total)
        while total and row_count == limit:
            data = self.search_read(offset=offset, limit=limit)
            row_count = len(data) if data else 0
            if row_count == 0:
                break
            _logger.info("Count %s ,Offset %s, Total: %s", row_count, offset, total)
            for item in data:
                offset = offset + 1
                # self.ids = [item.get('id')]
                call_back(item, offset=offset, total=total)

        _logger.info("Done : Offset %s = total %s", offset, total)

    def __str__(self):
        return "remote.RemoteModel({})".format(self.model_name)

    __repr__ = __str__


# =========================
# CORE Remote
# =========================
class OdooSession(requests.Session):
    def __init__(self, auth_model, base_path=None, rcp_path="/web/dataset/call_kw"):
        super().__init__()
        self.auth_model = auth_model
        self.base_path = base_path
        self.rcp_path = rcp_path

    def __enter__(self):
        self.connect()
        return self

    def get_endpoint_url(self):
        return self.auth_model.get_endpoint_url()

    def get_base_path(self):
        return self.base_path

    def get_rcp_path(self):
        return self.rcp_path

    def get_rest_url(self, path=None):
        return rest_url(self.get_endpoint_url(), self.get_base_path(), path)

    def connect(self):
        self.auth_model.connect_session(self)

    def request(self, *args, **kwargs):
        resp = super().request(*args, **kwargs)

        if resp.status_code == 401:
            self.cookies.clear()
            self.auth_model.reconnect_session(self)
            return super().request(*args, **kwargs)

        return resp

    def jsonrpc_call(self, model_name, method, args, kw=None):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model_name,
                "method": method,
                "args": args or [],
                "kwargs": kw or {}
            }
        }
        url = rest_url(self.get_endpoint_url(), self.get_rcp_path())
        resp = self.post(url, json=normalize_json(payload))
        resp.raise_for_status()
        data = resp.json()

        # JSON-RPC error
        if "error" in data:
            raise RuntimeError(f"Odoo login error: {data['error']}")

        return data.get("result") or []

    def create_remote_model(self, model_name, **kwargs):
        if self.auth_model.auth_type in ('odoo-rcp',):
            remote_model = JsonRPCRemoteModel(model_name, self, **kwargs)
        else:
            remote_model = RestModelObject(model_name, self, **kwargs)
        return remote_model


class JsonRPCRemoteModel(RemoteModel):
    def __init__(self, model_name, session: OdooSession, **kwargs):
        super().__init__(model_name, **kwargs)
        self.session = session

    def call(self, method, args, kw=None):
        return self.session.jsonrpc_call(self.model_name, method, args, kw=kw)

    def __getattr__(self, method):
        def delegate_func(*args, **kw):
            return self.call(method, args, kw=kw)

        return delegate_func


class JsonRPCSessionModelObject(JsonRPCRemoteModel):
    def __init__(self, model_name, session: OdooSession, **kwargs):
        super().__init__(model_name, session, **kwargs)
        self.session = session

    # menggunakan conext manager
    def __enter__(self):
        self.session.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.session.close()


class RestModelObject(RemoteModel):
    def __init__(self, model_name, session, **kwargs):
        super().__init__(model_name, **kwargs)
        self.session = session

    def rest_path_get(self, params=None):
        url = self.session.get_rest_url(self.model_name)
        return self.session.get(url, params=params)

    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, context=None):
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

        context = context or self.context
        if context:
            params['context'] = str(context)

        response = self.rest_path_get(params=params)
        return response.json().get("results", [])

    def read(self, ids=None, fields=None):
        if not ids and self.ids and isinstance(self.ids, (list, tuple)):
            ids = self.ids[0]
        params = {}
        fields = fields or self.fields
        if ids is not None:
            params['ids'] = str(ids)
        if fields is not None:
            params['fields'] = str(fields)
        if self.context:
            params['context'] = str(self.context)
        response = self.rest_path_get(params=params)
        return response.json().get("results", [])

    def search_count(self):
        params = {}
        if self.domain:
            params['domain'] = str(self.domain)
        if self.context:
            params['context'] = str(self.context)
        params['count'] = True
        response = self.rest_path_get(params=params)
        return response.json().get("count", 0)

    def __str__(self):
        return "client.RestModelObject({})".format(self.model_name)

    __repr__ = __str__
