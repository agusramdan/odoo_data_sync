# -*- coding: utf-8 -*-

from odoo.fields import Datetime, Date
from datetime import date, datetime, timedelta
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


# HELEPER
def get_db_name(url):
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("db")
    except Exception as e:
        _logger.error(f"Error get default db name {url}: {e}")
    return None


def odoo_rpc_auth(self, odoo_session, odoo_server_db, username, password):
    # 1. Authenticate
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [odoo_server_db, username, password, {}]
        },
        "id": 1,
    }
    resp = odoo_session.post(
        f"{self.get_endpoint_url()}/jsonrpc",
        json=payload
    )
    resp.raise_for_status()
    data = resp.json()

    # JSON-RPC error
    if "error" in data:
        raise RuntimeError(f"Odoo login error: {data['error']}")

    uid = data.get("result")
    if not uid:
        raise RuntimeError("Odoo login failed: invalid credentials")

    self.odoo_server_uid = uid
    return uid


def odoo_rpc_session_auth(self, odoo_session, odoo_server_db, username, password):
    payload = {
        "jsonrpc": "2.0",
        "params": {
            "db": odoo_server_db,
            "login": username,
            "password": password
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
    uid = result.get("uid")
    # uid False / None
    if not uid:
        raise RuntimeError("Odoo login failed: invalid credentials")

    # valid session_id cookie
    if "session_id" not in odoo_session.cookies:
        raise RuntimeError("Odoo login failed: session_id not set")
        # simpan uid (cookie sudah otomatis di session)
    self.odoo_server_uid = uid
    return uid


def apply_odoo_rpc_token_auth(self, odoo_session):
    refresh_token_if_needed(self)
    odoo_server_db = self.get_db_name() or get_db_name(self.get_db_name_endpoint_url())
    if not odoo_server_db:
        raise ValueError("Odoo RPC auth requires database name")
    username = self.get_username()
    password = self.get_access_token()
    odoo_rpc_auth(self, odoo_session, odoo_server_db, username, password)


def apply_odoo_rpc_auth(self, odoo_session):
    username, password = self.get_username_password()
    odoo_server_db = self.get_db_name() or get_db_name(self.get_db_name_endpoint_url())
    if not odoo_server_db:
        raise ValueError("Odoo RPC auth requires database name")
    odoo_rpc_session_auth(self, odoo_session, odoo_server_db, username, password)


def apply_auth(self, odoo_session: requests.Session):
    if self.auth_type in ('basic',):
        apply_basic_auth(self, odoo_session)
    elif self.auth_type in ('odoo-rcp',):
        apply_odoo_rpc_auth(self, odoo_session)
    elif self.auth_type in ('jwt-odoo-rcp',):
        apply_odoo_rpc_token_auth(self, odoo_session)
    elif self.auth_type in ('token', 'rest-token', 'jwt-rest-token'):
        apply_token_auth(self, odoo_session)
    else:
        raise ValueError(f"Unsupported auth_type: {self.auth_type}")


def apply_basic_auth(self, odoo_session):
    odoo_session.auth = self.get_username_password()


def apply_token_auth(self, odoo_session):
    refresh_token_if_needed(self)

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


def refresh_token_if_needed(self):
    refresh_endpoint = self.get_token_endpoint_url()
    if not refresh_endpoint or not self.refresh_token:
        return

    if self.expires_at and datetime.now().replace(microsecond=0) < self.expires_at:
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
    expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    self.update_token(data.get("access_token"), data.get("refresh_token"), expires_at)


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
        if not path.startswith('/'):
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
    def __init__(self, auth_model, base_path='/api/sync/data', rcp_path=None):
        super().__init__()
        self.auth_model = auth_model
        self.session_rpc = auth_model.get_auth_type() in ('odoo-rcp',)
        if rcp_path is None and self.session_rpc:
            rcp_path = "/web/dataset/call_kw"
        else:
            rcp_path = "/jsonrpc"
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
        if self.session_rpc:
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
        else:
            db, uid, username, password = self.auth_model.get_db_uid_username_password()
            if not db:
                db = get_db_name(self.auth_model.get_db_name_endpoint_url())
                if not db:
                    raise ValueError("Odoo RPC call requires database name")
            if not uid:
                uid = odoo_rpc_auth(self.auth_model, self, db, username, password)
                if not uid:
                    raise ValueError("Odoo RPC call requires valid uid")

            if not all([db, uid, password]):
                raise ValueError("Odoo RPC call requires database name, uid, and password")

            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [db, uid, password, model_name, method, args, kw],
                },
                "id": 2,
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
        kw = dict(kw or {})
        context = self.context or {}
        if 'context' in kw:
            context.update(kw['context'] or {})
        kw['context'] = context
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
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

    def read(self, ids=None, fields=None):
        # if not ids and self.ids and isinstance(self.ids, (list, tuple)):
        #     ids = self.ids[0]
        params = {}
        fields = fields or self.fields
        if ids is not None:
            params['ids'] = str(ids)
        if fields is not None:
            params['fields'] = str(fields)
        if self.context:
            params['context'] = str(self.context)
        response = self.rest_path_get(params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

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
        return "remote.RestModelObject({})".format(self.model_name)

    __repr__ = __str__


# =========================

if __name__ == "__main__":
    class AuthModel:
        def __init__(self, auth_type, username, password=None, access_token=None, refresh_token=None, expires_at=None):
            self.auth_type = auth_type
            self.username = username
            self.password = password
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.expires_at = expires_at

        def get_db_name(self):
            return None

        def get_username(self):
            return self.username

        def get_password(self):
            return self.password

        def get_access_token(self):
            return self.access_token

        def get_username_password(self):
            return self.username, self.password

        def get_db_uid_username_password(self):
            access_token = self.password or self.get_access_token()
            return None, None, self.username, access_token

        def get_db_username_password(self):
            access_token = self.password or self.get_access_token()
            return None, self.username, access_token

        def get_auth_type(self):
            return self.auth_type

        def get_endpoint_url(self):
            return "http://localhost:8069"

        def get_odoo_db_name_path(self):
            return '/sync/db_name'

        def get_token_endpoint_url(self):
            return f"{self.get_endpoint_url()}/application/token"

        def get_db_name_endpoint_url(self):
            return f"{self.get_endpoint_url()}{self.get_odoo_db_name_path()}"

        def connect_session(self, odoo_session):
            apply_auth(self, odoo_session)

        def reconnect_session(self, odoo_session):
            apply_auth(self, odoo_session)

        def update_token(self, access_token, refresh_token=None, expires_at=None):
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.expires_at = expires_at

    auth_model = AuthModel('basic', 'admin', 'admin')
    session_auth = OdooSession(auth_model)
    session_auth.connect()

    remote_rest_partner = RestModelObject("res.partner", session_auth, context={'lang': 'en_US'})
    partners = remote_rest_partner.search_read(limit=10)
    print("WITHOUT SESSION MODE search_read:", partners)
    partners = remote_rest_partner.read([1, 2, 3, 4], fields=['name', 'email'])
    print("WITHOUT SESSION MODE read:", partners)

    auth_model2 = AuthModel('jwt-odoo-rcp', 'admin', access_token='admin')
    session_auth2 = OdooSession(auth_model2)
    session_auth2.connect()
    remote_partner = JsonRPCRemoteModel("res.partner", session_auth2, context={'lang': 'en_US'})
    partners = remote_partner.search_read(limit=10)
    print("TOKEN MODE search_read:", partners)
    partners = remote_partner.read([1, 2, 3, 4], fields=['name', 'email'])
    print("TOKEN MODE read:", partners)

    auth_model3 = AuthModel('odoo-rcp', 'admin', password='admin')
    # ---- SESSION MODE ----
    session_auth3 = OdooSession(auth_model3)
    session_auth3.connect()

    remote_partner = JsonRPCRemoteModel("res.partner", session_auth3, context={'lang': 'en_US'})
    partners = remote_partner.search_read(limit=10)
    print("SESSION MODE search_read:", partners)
    partners = remote_partner.read([1, 2, 3, 4], fields=['name', 'email'])
    print("SESSION MODE read:", partners)
