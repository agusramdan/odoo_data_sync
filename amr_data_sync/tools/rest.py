import datetime
import logging
import hashlib
import os
import werkzeug.wrappers
from odoo import fields
try:
    import simplejson as json
except ImportError:
    import json

_logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8")
        if isinstance(obj, datetime.datetime):
            return fields.Datetime.to_string(obj)
        if isinstance(obj, datetime.date):
            return fields.Date.to_string(obj)
        return json.JSONEncoder.default(self, obj)


def valid_response(status, data):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps(data, cls=JSONEncoder),
    )


def invalid_response(status, error, info):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps({
            'error': error,
            'error_desc': info,
        }),
    )


def invalid_object_id():
    _logger.error("Invalid object 'id'!")
    return invalid_response(400, 'invalid_object_id', "Invalid object 'id'!")


def invalid_token():
    _logger.error("Token is expired or invalid!")
    return invalid_response(401, 'invalid_token', "Token is expired or invalid!")


def model_not_found(modal_name):
    _logger.error("Not found object(s) in system!")
    return invalid_response(404, 'object_not_found_in_system',
                            "Modal " + modal_name + " Not Found!")


def rest_api_unavailable(modal_name):
    _logger.error("Not found object(s) in system!")
    return invalid_response(404, 'object_not_found_in_system',
                            "Enable Rest API For " + modal_name + "!")


def object_not_found_all(modal_name):
    _logger.error("Not found object(s) in system!")
    return invalid_response(404, 'object_not_found_in_system',
                            "No Record found in " + modal_name + "!")


def object_not_found(record_id, modal_name):
    _logger.error("Not found object(s) in system!")
    return invalid_response(404, 'object_not_found_in_system',
                            "Record " + str(record_id) + " Not found in " + modal_name + "!")


def unable_delete():
    _logger.error("Access Denied!")
    return invalid_response(
        403, "you don't have access to delete records for "
             "this model", "Access Denied!")


def no_object_created(system_error):
    _logger.error("Not created object in system! ERROR: %s" % system_error)
    return invalid_response(
        500, 'not_created_object_in_system',
        "Not created object in system! ERROR: %s" %
        system_error)


def no_object_updated(system_error):
    _logger.error("Not updated object in system! ERROR: %s" % system_error)
    return invalid_response(
        500, 'not_updated_object_in_system',
        "Object Not Updated! ERROR: %s" %
        system_error)


def no_object_deleted(system_error):
    _logger.error("Not deleted object in system! ERROR: %s" % system_error)
    return invalid_response(
        500, 'not_deleted_object_in_system',
        "Not deleted object in system! ERROR: %s" %
        system_error)


def generate_token(length=40):
    random_data = os.urandom(100)
    hash_gen = hashlib.new('sha512')
    hash_gen.update(random_data)
    return hash_gen.hexdigest()[:length]
