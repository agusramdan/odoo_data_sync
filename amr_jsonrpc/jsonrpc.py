from odoo.exceptions import UserError
from odoo import _
import requests
import logging

_logger = logging.getLogger(__name__)


def post(jsonrpc_url, obj_payload, raise_exception=True):
    response = requests.post(jsonrpc_url, json=obj_payload)
    raise_exception and response.raise_for_status()
    return response.json()


def authenticate(jsonrpc_url, db, username, password, raise_exception=False):
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
    res = post(jsonrpc_url, auth_payload, raise_exception=raise_exception)
    uid = res.get("result")
    if not uid and raise_exception:
        raise UserError(_("Authentication failed. Please check your credentials."))
    return db, uid, password


def execute_kw(jsonrpc_url, model, method, args, kw=None, db=None, uid=None, password=None):
    obj_payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [db, uid, password, model, method, args, kw],
        },
        "id": 2,
    }
    try:
        json_data = post(jsonrpc_url, obj_payload)
        if "error" in json_data:
            raise Exception(f"Odoo Error: {json_data['error']}")
        return json_data.get("result")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network Error: {str(e)}")
    except Exception as e:
        raise Exception(f"Unexpected Error: {str(e)}")


class ModelObject(object):
    def __init__(self, model_name, **kwargs):

        self.model_name = model_name
        self.endpoint_url = kwargs.get('endpoint_url')
        self.db = kwargs.get('db')
        self.uid = kwargs.get('uid')
        self.username = kwargs.get('username')
        self.password = kwargs.get('password')
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

    def __getattr__(self, method):
        def delegate_func(*args, **kw):
            args = list(args)
            if self.ids is not None:
                args = [self.ids] + args
            url, db, uid, password = self.get_url_db_uid_password()
            return execute_kw(
                url, self.model_name, method, args=args, kw=kw, db=db, uid=uid, password=password
            )

        return delegate_func

    def browse(self, ids):
        if ids and isinstance(ids, int):
            ids = [ids]
        else:
            ids = ids or []
        return self.copy(
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

    def get_url_db_username_password(self):
        return self.get_endpoint_url(), self.get_db(), self.get_username(), self.get_password()

    def get_url_db_uid_password(self):
        self.ensure_authenticate()
        return self.get_endpoint_url(), self.get_db(), self.uid, self.get_password()

    def ensure_authenticate(self):
        if not self.uid:
            url, db, username, password = self.get_url_db_username_password()
            db, self.uid, password = authenticate(url, db, username, password, True)
        return self

    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        model_name = self.model_name
        method = 'search_read'
        args = []
        kw = {
            'domain': domain or self.domain,
            'fields': fields or self.fields, 'order': order or self.order,
            'offset': offset or self.offset, 'limit': limit or self.limit,
        }
        url, db, uid, password = self.get_url_db_uid_password()
        return execute_kw(
            url, model_name, method, args=args, kw=kw, db=db, uid=uid, password=password
        )

    def read(self, fields=None, _id=None):
        if not _id and self.ids and isinstance(self.ids, (list, tuple)):
            _id = self.ids[0]
        if not _id:
            raise Exception("No _id can not call read")
        model_name = self.model_name
        method = 'read'
        args = [[_id]]
        kw = {'fields': fields or self.fields}
        url, db, uid, password = self.get_url_db_uid_password()
        return execute_kw(
            url, model_name, method, args=args, kw=kw, db=db, uid=uid, password=password
        )

    def search_count(self):
        model_name = self.model_name
        method = 'search_count'
        args = [self.domain or []]
        url, db, uid, password = self.get_url_db_uid_password()
        return execute_kw(
            url, model_name, method, args=args, db=db, uid=uid, password=password
        )

    def external_data_callback(self, call_back):
        total = self.search_count()
        offset = 0
        row_count = self.limit
        limit = self.limit
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
        return "jsonrpc.ModelObject({})".format(self.model_name)

    __repr__ = __str__


def model_object(model, **kwargs):
    obj = ModelObject(model, **kwargs)
    return obj.ensure_authenticate()
