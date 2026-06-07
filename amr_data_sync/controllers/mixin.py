# -*- coding: utf-8 -*-

import json
import logging

from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response
from odoo.http import request
from ..exceptions.api_exception import ApiException

_logger = logging.getLogger(__name__)


class ApiControllerMixin(object):

    @classmethod
    def get_json_payload(cls):
        body = request.httprequest.data
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    @classmethod
    def json_response(cls, result, status=200):
        return Response(
            json.dumps(result),
            headers=[
                ("Content-Type", "application/json")
            ],
            status=status,
        )

    @classmethod
    def json_success(cls, data, status=200):
        return cls.json_response(
            {
                "success": True,
                "data": data,
            },
            status=status
        )

    @classmethod
    def json_exception(cls, ex: ApiException):
        _logger.error(ex)
        return cls.json_response(
            ex.to_dict(),
            status=ex.status,
        )

    @classmethod
    def json_unknown_exception(cls, ex):
        _logger.exception(ex)
        return cls.json_response(
            {
                "success": False,
                "error": "unknown_error",
                "error_description": "Unknown error.",
            },
            status=500,
        )

    @classmethod
    def handle_exception(cls, ex):
        if isinstance(ex, ApiException):
            return cls.json_response(
                ex.to_dict(),
                status=ex.status,
            )
        if isinstance(ex, HTTPException):
            raise ex
        return cls.json_response(
            {
                "success": False,
                "error": "general_error",
                "error_description": str(ex),
            },
            status=500,
        )
