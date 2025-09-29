# -*- coding: utf-8 -*-

import functools
import ast

from odoo.exceptions import AccessDenied

try:
    import simplejson as json
except ImportError:
    import json
import odoo
from odoo import http
from odoo.http import request

from ..tools.rest import *

_logger = logging.getLogger(__name__)


def eval_json_to_data(modelname, json_data, create=True):
    Model = request.env[modelname]
    model_fiels = Model._fields
    field_name = [name for name, field in Model._fields.items()]
    values = {}
    for field in json_data:
        if field not in field_name:
            continue
        if field not in field_name:
            continue
        val = json_data[field]
        if not isinstance(val, list):
            values[field] = val
        else:
            values[field] = []
            if not create and isinstance(model_fiels[field], fields.Many2many):
                values[field].append((5,))
            for res in val:
                recored = {}
                for f in res:
                    recored[f] = res[f]
                if isinstance(model_fiels[field], fields.Many2many):
                    values[field].append((4, recored['id']))

                elif isinstance(model_fiels[field], odoo.fields.One2many):
                    if create:
                        values[field].append((0, 0, recored))
                    else:
                        if 'id' in recored:
                            id = recored['id']
                            del recored['id']
                            values[field].append((1, id, recored)) if len(recored) else values[field].append((2, id))
                        else:
                            values[field].append((0, 0, recored))
    return values


def object_read(model_name, params, status_code):
    domain = []
    fields = None
    offset = 0
    limit = None
    order = None
    if 'filters' in params:
        domain += ast.literal_eval(params['filters'])
    if 'field' in params:
        fields += ast.literal_eval(params['field'])
    if 'offset' in params:
        offset = int(params['offset'])
    if 'limit' in params:
        limit = int(params['limit'])
    if 'order' in params:
        order = params['order']

    ModelObject = request.env[model_name].with_context(__from_sync_data_api=True)

    data = ModelObject.search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order)

    if data:
        return valid_response(status=status_code, data={
            'count': len(data),
            'results': data
        })
    else:
        return object_not_found_all(model_name)


def object_read_one(model_name, rec_id, params, status_code):
    fields = []
    if 'field' in params:
        fields += ast.literal_eval(params['field'])
    try:
        rec_id = int(rec_id)
    except Exception as e:
        rec_id = False

    if not rec_id:
        return invalid_object_id()
    ModelObject = request.env[model_name].with_context(__from_sync_data_api=True)

    data = ModelObject.search_read(domain=[('id', '=', rec_id)], fields=fields)

    if data:
        return valid_response(status=status_code, data=data)
    else:
        return object_not_found(rec_id, model_name)


def object_create_one(model_name, data, status_code):
    try:
        ModelObject = request.env[model_name].with_context(__from_sync_data_api=True)
        res = ModelObject.create(data)
    except Exception as e:
        return no_object_created(e)
    if res:
        return valid_response(status_code, {'id': res.id})


def object_update_one(model_name, rec_id, data, status_code):
    try:
        rec_id = int(rec_id)
    except Exception as e:
        rec_id = None

    if not rec_id:
        return invalid_object_id()

    try:
        ModelObject = request.env[model_name].with_context(__from_sync_data_api=True)
        res = ModelObject.search([('id', '=', rec_id)])
        if res:
            res.write(data)
        else:
            return object_not_found(rec_id, model_name)
    except Exception as e:
        return no_object_updated(e)
    if res:
        return valid_response(status_code, {'desc': 'Record Updated successfully!', 'update': True})


def object_delete_one(model_name, rec_id, status_code):
    try:
        rec_id = int(rec_id)
    except Exception as e:
        rec_id = None

    if not rec_id:
        return invalid_object_id()

    try:
        res = request.env[model_name].search([('id', '=', rec_id)])
        if res:
            res.unlink()
        else:
            return object_not_found(rec_id, model_name)
    except Exception as e:
        return no_object_deleted(e)
    if res:
        return valid_response(status_code, {'desc': 'Record Successfully Deleted!', 'delete': True})


"""
2025-08-28 03:03:45,369 28428 INFO DEV_13 odoo.addons.base.models.ir_http: Exception during request Authentication.
Traceback (most recent call last):
  File "{odoo_home}\odoo\addons\base\models\ir_http.py", line 115, in _authenticate
    request.session.check_security()
  File "{odoo_home}\odoo\http.py", line 1055, in check_security
    if not security.check_session(self, env):
  File "{odoo_home}\odoo\service\security.py", line 27, in check_session
    if expected and odoo.tools.misc.consteq(expected, session.session_token ):
TypeError: unsupported operand types(s) or combination of types: 'str' and 'NoneType'

"""


# _original_check_security = OpenERPSession.check_security
#
# def custom_check_security(self):
#     if request and request.httprequest and request.httprequest.path:
#         path = request.httprequest.path
#         if self.uid and not self.session_token:
#             _logger.warning("Session tanpa token dianggap expired API route %s", path)
#             raise SessionExpiredException("Session expired")
#
#     _original_check_security(self)
# # Replace method
# OpenERPSession.check_security = custom_check_security
#
def check_valid_token(func):
    @functools.wraps(func)
    def wrap(self, *args, **kwargs):
        access_token = request.httprequest.headers.get('access_token') or request.httprequest.headers.get('token')
        if not access_token:
            info = "Missing access token in request header!"
            error = 'access_token_not_found'
            _logger.error(info)
            return invalid_response(400, error, info)

        access_token_data = request.env['sync.access_token'].sudo().search(
            [('token', '=', access_token)], order='id DESC', limit=1)

        if access_token_data._get_access_token(user_id=access_token_data.user_id.id) != access_token:
            info = "Token is expired or invalid!"
            error = 'invalid_token'
            _logger.error(info)
            return invalid_response(401, error, info)
        # kwargs.update({'sync_token_data': access_token_data})
        user_id = access_token_data.user_id
        if user_id and request.session.uid != user_id.id:
            request.session.uid = user_id.id
            request.uid = user_id.id

        # set request.session.uid kaena akan ada kemungkinan  session_token None
        # ini bisa meyembabkan error di check_security
        # request.session.uid = access_token_data.user_id.id
        # request.uid = access_token_data.user_id.id
        if request.session.uid and not request.session.session_token:
            request.session.session_token = user_id._compute_session_token(request.session.sid)

        return func(self, *args, **kwargs)

    return wrap


db_name = odoo.tools.config.get('db_name')
if not db_name:
    _logger.warning("Warning: To proper setup OAuth - it's necessary to "
                    "set the parameter 'db_name' in odoo config file!")


# HTTP controller of REST resources:
def get_http_body():
    data = request.httprequest.data.decode("utf-8")  # raw body string
    try:
        json_data = json.loads(data)  # parse manual
    except Exception:
        json_data = {}
    return json_data


class ControllerREST(http.Controller):

    @http.route([
        '/api/sync/authenticate',
    ], type='http', auth="none", methods=['POST'], csrf=False)
    def rest_api_sync_authenticate(self, **post):
        body = get_http_body()
        login = post.get('login') or body.get('login')
        password = post.get('password') or body.get('password')
        session = request.session
        try:
            session.authenticate(db_name, login, password)
        except AccessDenied as e:
            return invalid_response(401, 'access_denied', str(e))

        data = {
            'uid': session.uid,
            'sid': session.sid,
            'db': session.db,
            'session_token': session.session_token,
        }
        return valid_response(200, data)

    @http.route([
        '/api/sync/data/<model_name>',
        '/api/sync/data/<model_name>/<id>'
    ], type='http', auth="none", methods=['GET'], csrf=False)
    @check_valid_token
    def rest_api_sync_data_access_token(self, model_name=False, id=False, **post):
        Model = request.env['ir.model']
        Model_id = Model.sudo().search([('model', '=', model_name)], limit=1)

        if Model_id:
            method = request.httprequest.method.lower()
            if (Model_id.is_sync_data_api and method == 'get') or (
                    Model_id.is_create_data_api and method == 'post') or (
                    Model_id.is_write_data_api and method == 'put') or (
                    Model_id.is_unlink_data_api and method == 'delete'):
                if method == 'delete':
                    return object_delete_one(model_name, id, status_code=200)
                if method == 'put':
                    return object_update_one(model_name, id, post, status_code=200)
                elif method == 'post':
                    return object_create_one(model_name, post, status_code=201)
                elif method == 'get':
                    if id:
                        return object_read_one(model_name, id, post, status_code=200)
                    else:
                        return object_read(model_name, post, status_code=200)
            else:
                return rest_api_unavailable(model_name)
        return model_not_found(model_name)
