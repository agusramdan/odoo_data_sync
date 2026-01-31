# -*- coding: utf-8 -*-

from odoo.fields import Datetime, Date
from datetime import datetime, date
from odoo.http import request
from odoo.exceptions import AccessError
from odoo.service import security
from functools import wraps
from werkzeug.wrappers import Response

import ast
import werkzeug.wrappers
import base64

try:
    import simplejson as json
except ImportError:
    import json

import logging


_logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8")
        if isinstance(obj, datetime):
            return Datetime.to_string(obj)
        if isinstance(obj, date):
            return Date.to_string(obj)
        return super().default(obj)


def set_session(login, uid, session_token=None):
    session = request.session
    session.rotate = True
    session.uid = uid
    session.login = login
    if login or uid:
        session.session_token = security.compute_session_token(session, request.env)
    else:
        session.session_token = session_token
    if not session.session_token:
        request.uid = None
        session.uid = None
        session.login = None
    else:
        request.uid = uid
        request.disable_db = False
        session.get_context()


def get_bearer_token():
    auth = request.httprequest.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth.split(" ", 1)[1]


def get_basic_auth():
    auth = request.httprequest.headers.get('Authorization')
    if not auth:
        return None, None

    try:
        scheme, encoded = auth.split(' ', 1)
        if scheme.lower() != 'basic':
            return None, None

        decoded = base64.b64decode(encoded).decode('utf-8')
        return decoded.split(':', 1)
    except Exception:
        return None, None


def make_response_error(status=400, error="", error_description=""):
    return Response(
        json.dumps({"error": error, 'error_description': error_description}),
        status=status,
        headers=[("Content-Type", "application/json")]
    )


def check_authorization(_func=None, *, setup_session=False, header_name=('token', 'access_token'), param_name=None):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            error = {}
            session = request.session
            save_uid = session.uid or request.uid
            save_login = session.login
            session_token = session.session_token
            accept_authorization = False
            try:
                username, password = get_basic_auth()
                uid = request.session.authenticate(
                    request.session.db,
                    username,
                    password
                )
            except:
                uid = None
            if uid:
                accept_authorization = True
            else:
                # Ambil semua kemungkin token yang ada
                token_list = [get_bearer_token()]
                header_names = []
                if header_name:
                    if isinstance(header_name, str):
                        header_names = [header_name]
                    elif isinstance(header_name, (list, tuple)):
                        header_names = header_name
                for name in header_names:
                    token_list.append(request.httprequest.headers.get(name))
                if param_name:
                    params = []
                    if isinstance(param_name, str):
                        params.append(param_name)
                    elif isinstance(param_name, (list, tuple)):
                        params.extend(param_name)
                    for p in params:
                        token_list.append(request.params.get(p))
                        token_list.append(kwargs.get(p))

                tokens = set(token_list)

                for t in tokens:
                    if not t:
                        continue
                    token_data = request.env['token.validator.service'].sudo().validate_token(t)
                    if token_data and token_data.get('uid'):
                        uid = token_data['uid']
                        login = token_data.get('username') or token_data.get('sub')
                        if uid and login:
                            accept_authorization = True
                            if setup_session:
                                set_session(login, uid)
                    if accept_authorization:
                        break
            if not accept_authorization:
                return invalid_response(
                    401, error.get("error", "invalid_token"),
                    error.get("error_description", "The token is invalid or expired.")
                )
            result = func(self, *args, **kwargs)
            if uid or setup_session:
                # Set kembali session sebelumnya
                set_session(save_uid, save_login, session_token)
            return result
        return wrapper

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def valid_response(status, data):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps(data, cls=JSONEncoder),
    )


def invalid_response(status, error, info=""):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps({
            'error': error,
            'error_description': info,
        }),
    )


def modal_not_found(modal_name):
    _logger.error("Not found object(s) in odoo!")
    return invalid_response(
        404, 'object_not_found_in_odoo', "Modal " + modal_name + " Not Found!"
    )


def rest_api_unavailable(modal_name):
    _logger.error("Not found object(s) in odoo!")
    return invalid_response(
        404, 'object_not_found_in_odoo', "Enable Rest API For " + modal_name + "!"
    )


def object_not_found_all(modal_name):
    _logger.error("Not found object(s) in odoo!")
    return invalid_response(
        404, 'object_not_found_in_odoo', "No Record found in " + modal_name + "!"
    )


def object_read(model_name, params, status_code, filter_fields=None, __from_sync_data_api=True, sudo_read=False):
    domain = []
    fields = []
    offset = 0
    limit = 100
    order = None
    ids = []
    if 'filters' in params:
        domain += ast.literal_eval(params['filters'])
    if 'context' in params:
        context = ast.literal_eval(params['context']) or {}
    else:
        context = {}
    if "__from_sync_data_api" not in context:
        context.update({'__from_sync_data_api': __from_sync_data_api})

    model = request.env[model_name].with_context(context)
    if sudo_read:
        model = model.sudo(sudo_read)

    if 'count' in params:
        count = ast.literal_eval(params['count']) or False
    else:
        count = False

    if count:
        data_count = model.search_count(domain)
        return valid_response(status=status_code, data={
            'count': data_count,
        })

    if 'fields' in params:
        fields += ast.literal_eval(params['fields'])

    if 'ids' in params:
        ids = ast.literal_eval(params['ids']) or []
        if ids:
            data = model.browse(ids).read(fields)
            return valid_response(status=status_code, data={
                'count': len(data),
                'results': data
            })

    if 'offset' in params:
        offset = int(params['offset'])
    if 'limit' in params:
        limit = int(params['limit'])
    if 'order' in params:
        order = params['order']

    if filter_fields:
        fields = filter_fields(model_name, fields)

    try:
        data = model.search_read(
                domain=domain, fields=fields, offset=offset, limit=limit, order=order
            )
        if data:
            return valid_response(status=status_code, data={
                'count': len(data),
                'results': data
            })
        else:
            return object_not_found_all(model_name)
    except AccessError as e:
        _logger.error("Error: %s" % e.name)
        return invalid_response(
            403, "you don't have access to read records for " "this model", "Error: %s" % e.name
        )
    except Exception as e:
        return invalid_response(
            500, "Process error please contact Administrator", "Error: %s" % str(e)
        )
