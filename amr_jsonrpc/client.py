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


# =========================
# CORE CLIENT
# =========================
class OdooClient:

    def __init__(self, base_url):
        self.base_url = base_url and base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.auth = self

    def call_kw(self, model, method, args, kw):
        raise NotImplemented

    def execute_kw(self, model, method, args, kw):
        json_data = self.call_kw(model, method, args, kw)
        if "error" in json_data:
            raise Exception(f"Odoo Error: {json_data['error']}")
        return json_data.get("result")

    def rest_url(self, path):
        return f"{self.base_url}/{path}" if path and path not in ['', '/'] else self.base_url

    def rest_post(self, path=None, data=None, json=None, **kwargs):
        return self.session.post(self.rest_url(path), data=data, json=json, **kwargs)

    def rest_get(self, path=None, **kwargs):
        return self.session.get(self.rest_url(path), **kwargs)

    def get_odoo_client_rest_path(self, path):
        return OdooClientRestPath(self.auth, path)

    def create_remote_model(self, model_name, **kwargs):
        path = kwargs.get('path') or '/api/data/sync'
        path_model = f"/api/data/sync/{model_name}"
        client_rest_path = self.get_odoo_client_rest_path(path_model)
        return RestModelObject(model_name, client_rest_path, **kwargs)


class OdooClientRestPath:

    def __init__(self, auth, path):
        self.auth = auth
        self.path = path

    def rest_url(self, path):
        return self.auth.rest_url(path)

    def rest_path_post(self, data=None, json=None, **kwargs):
        return self.auth.rest_post(self.path, data=data, json=json, **kwargs)

    def rest_path_get(self, **kwargs):
        return self.auth.rest_get(self.path, **kwargs)

    def create_remote_model(self, model_name, **kwargs):
        client_rest_path = self.auth.get_odoo_client_rest_path(self.path)
        return RestModelObject(model_name, client_rest_path, **kwargs)


# =========================
# SESSION AUTH (NATIVE)
# =========================
class OdooSessionAuth(OdooClient):
    def __init__(self, base_url, db, login, password, uid=None):
        super().__init__(base_url)
        self.type = 'session'
        self.db = db
        self.login = login
        self.password = password
        self.uid = uid
        self.support_json_rcp = True

    def get_db_uid_password(self):
        return self.db, self.uid, self.password

    def login_session(self):
        payload = {
            "jsonrpc": "2.0",
            "params": {
                "db": self.db,
                "login": self.login,
                "password": self.password
            }
        }
        resp = self.session.post(
            f"{self.base_url}/web/session/authenticate",
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
        if "session_id" not in self.session.cookies:
            raise RuntimeError("Odoo login failed: session_id not set")

        return result

    def call_kw(self, model, method, args=None, kwargs=None):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args or [],
                "kwargs": kwargs or {}
            }
        }
        resp = self.session.post(
            f"{self.base_url}/web/dataset/call_kw",
            json=normalize_json(payload)
        )
        resp.raise_for_status()
        return resp.json()

    def create_remote_model(self, model_name, **kwargs):
        return JsonRPCModelObject(model_name, self, **kwargs)


# =========================
# TOKEN AUTH (CUSTOM API)
# =========================
class TokenAuth(OdooClient):
    def __init__(self, base_url, access_token,
                 refresh_token=None, refresh_endpoint=None, expires_at=None):
        super().__init__(base_url)
        self.type = 'token'
        self.access_token = access_token
        self.refresh_endpoint = refresh_endpoint
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.support_json_rcp = False

    def rest_post(self, path=None, data=None, json=None, **kwargs):
        def call_post():
            return super(TokenAuth, self).rest_get(path, data=data, json=json, **kwargs)

        return safe_call(call_post, self)

    def rest_get(self, path=None, **kwargs):
        def call_get():
            return super(TokenAuth, self).rest_get(path, **kwargs)

        return safe_call(call_get, self)

    # --- apply token ---
    def apply(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })

    # --- expired check ---
    def is_expired(self):
        return self.expires_at and datetime.utcnow() >= self.expires_at

    # --- refresh token ---
    def refresh(self):
        resp = self.session.post(
            self.refresh_endpoint, json={"refresh_token": self.refresh_token}
        )
        resp.raise_for_status()

        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = datetime.fromisoformat(data["expires_at"])

        self.apply()


class BasicAuth(OdooClient):

    def __init__(self, base_url, username, password, path=""):
        super().__init__(base_url)
        self.type = 'basic'
        self.username = username
        self.password = password
        self.path = path
        self.support_json_rcp = False

    def apply(self):
        self.session.auth = HTTPBasicAuth(self.username, self.password)


class TokenAuthBearer(OdooClient):
    def __init__(self, base_url, access_token, path=""):
        super().__init__(base_url)
        self.type = 'token'
        self.access_token = access_token
        self.path = path
        self.support_json_rcp = False

    # --- apply token ---
    def apply(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })


class HeaderTokenAuth(OdooClient):

    def __init__(self, base_url, header_name, token, path=""):
        super().__init__(base_url)
        self.type = 'header'
        self.header_name = header_name
        self.token = token
        self.path = path
        self.support_json_rcp = False

    def apply(self):
        self.auth.session.headers.update({
            self.header_name: self.token
        })


class ParamTokenAuth(OdooClient):
    def __init__(self, base_url, param_name, token, path=""):
        super().__init__(base_url)
        self.type = 'param'
        self.param_name = param_name
        self.token = token
        self.path = path
        self.support_json_rcp = False

    def with_token(self, params: dict):
        params = params or {}
        params[self.param_name] = self.token
        return params

    def rest_post(self, path=None, data=None, json=None, param=None, **kwargs):
        param = self.with_token(param)
        return super(ParamTokenAuth, self).rest_post(path, data=data, json=json, param=param, **kwargs)

    def rest_get(self, path=None, param=None, **kwargs):
        param = self.with_token(param)
        return super(ParamTokenAuth, self).rest_get(path=path, param=param, **kwargs)


class JsonRPCModelObject:
    def __init__(self, model_name, auth, **kwargs):
        self.auth = auth
        self.model_name = model_name
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
            'context': dict(self.context),
            'domain': list(self.domain),
            'fields': self.fields,
            'offset': self.offset,
            'limit': self.limit,
            'order': self.order,
            'ids': list(self.ids),
        }
        data.update(overrides)
        return JsonRPCModelObject(self.model_name, self.auth, **data)

    def model_object(self, model_name, **overrides):
        data = {
            'context': dict(self.context),
        }
        data.update(overrides)
        return JsonRPCModelObject(model_name, self.auth, **data)

    def call(self, method, args, kw=None):
        return self.auth.execute_kw(self.model_name, method, args, kw)

    def __getattr__(self, method):
        def delegate_func(*args, **kw):
            args = list(args)
            if self.ids:
                args = [self.ids] + args
            return self.call(method, args, kw=kw)

        return delegate_func

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
        if not args and self.ids and isinstance(self.ids, (list, tuple)):
            args = self.ids
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
        _logger.info("Start : get_external_data %s = total %s", self.model_name, total)
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
        return "client.JsonRPCModelObject({})".format(self.model_name)

    __repr__ = __str__


class RestModelObject:
    def __init__(self, model_name, path_client, **kwargs):
        self.path_client = path_client
        self.model_name = model_name
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
            'context': dict(self.context),
            'domain': list(self.domain),
            'fields': self.fields,
            'offset': self.offset,
            'limit': self.limit,
            'order': self.order,
            'ids': list(self.ids),
        }
        data.update(overrides)
        return RestModelObject(self.model_name, self.path_client, **data)

    def model_object(self, model_name, **overrides):
        data = {
            'context': dict(self.context),
        }
        data.update(overrides)
        return RestModelObject(model_name, self.path_client, **data)

    def browse(self, ids):
        if ids and isinstance(ids, int):
            ids = [ids]
        else:
            ids = ids or []
        return self.copy_model(
            ids=ids
        )

    def copy_model(self, **kwargs):
        return RestModelObject(self.model_name, self.auth, **kwargs)

    def rest_path_get(self, params=None):
        return self.path_client.rest_path_get(params=params)

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
        return "client.RestModelObject({})".format(self.model_name)

    __repr__ = __str__


# =========================
# EXAMPLE USAGE
# =========================
if __name__ == "__main__":
    # ---- SESSION MODE ----
    session_auth = OdooSessionAuth(
        "http://localhost:8069",
        db="DEV_13",
        login="admin",
        password="admin"
    )
    session_auth.login_session()

    remote_partner = JsonRPCModelObject("res.partner", session_auth)
    partners = remote_partner.search_read()

    print("SESSION MODE:", partners)
    partners = remote_partner.write(
        [7], {'name': datetime.now()}
    )
    print("SESSION MODE write:", partners)
    # ---- TOKEN MODE ----
    # token_auth = TokenAuth(client)
    # token_auth.access_token = "ACCESS_TOKEN"
    # token_auth.refresh_token = "REFRESH_TOKEN"
    # token_auth.expires_at = datetime.utcnow()
    # token_auth.apply()
    #
    # data = safe_call(
    #     lambda: client.session.get(f"{client.base_url}/api/data").json(),
    #     token_auth
    # )
    #
    # print("TOKEN MODE:", data)
