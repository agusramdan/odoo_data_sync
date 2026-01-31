# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from ..tools.utils import check_authorization, modal_not_found, rest_api_unavailable, object_read

import logging

_logger = logging.getLogger(__name__)


class ControllerSync(http.Controller):

    @http.route([
        '/api/sync/data/<model_name>'
    ], type='http', auth="none", methods=['GET'], csrf=False)
    @check_authorization(setup_session=True)
    def rest_api_sync_data(self, model_name, **kwargs):
        Model = request.env['ir.model']
        Model_id = Model.sudo().search([('model', '=', model_name)], limit=1)
        if not Model_id:
            return modal_not_found(model_name)
        if Model_id.excluded_read_sync_api() or not Model_id.is_read_sync_api():
            return rest_api_unavailable(model_name)

        return object_read(
            model_name, kwargs,
            status_code=200, sudo_read=Model_id.sudo_read_sync_api()
        )
