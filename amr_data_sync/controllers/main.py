# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request, route
from .mixin import ApiControllerMixin

_logger = logging.getLogger(__name__)

class DataUpdateController(http.Controller, ApiControllerMixin):

    @route("/api/v1/data/update", type="http", auth="machine", methods=["POST"], csrf=False, )
    def data_update(self, **kwargs):
        try:
            payload = self.get_json_payload()
            result = request.env["data.update.service"].sudo().data_update(payload,)
            return self.json_success(result)
        except Exception as ex:
            _logger.exception("Exception error")
            return self.handle_exception(ex)


