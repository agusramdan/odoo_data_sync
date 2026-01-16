# -*- coding: utf-8 -*-

from odoo import http, tools
from odoo.http import request

import logging
import werkzeug

try:
    import simplejson as json
except ImportError:
    import json

_logger = logging.getLogger(__name__)

db_name = tools.config.get('db_name')
if not db_name:
    _logger.warning("Warning: To proper setup db_name - it's necessary to "
                    "set the parameter 'db_name' in odoo config file!"
                    )


class ControllerREST(http.Controller):

    @http.route([
        '/sync/db_name',
    ], type='http', auth="none", methods=['GET'], csrf=False)
    def rest_api_sync_db_name(self):
        data = {
            'db': request.session.db,
        }
        return werkzeug.wrappers.Response(
            status=200,
            content_type='application/json; charset=utf-8',
            response=json.dumps(data),
        )
