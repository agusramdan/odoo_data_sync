# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, api
from odoo.addons.base.models.ir_fields import exclude_ref_fields
from odoo.exceptions import UserError, AccessDenied
from odoo.tools import image_process
import json
import logging
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = {}
        if isinstance(item, list):
            if len(item) > 0:
                item_dict['id'] = item[0]
            if len(item) > 1:
                item_dict['name'] = item[1]
        elif isinstance(item, dict):
            item_dict = item

        if item_dict:
            if item_dict.get('id') in [1, 2, 3, 4]:
                return self.sudo().browse(item_dict.get('id'))
            elif item_dict.get('email'):
                return self.sudo().search([('email', '=', item_dict.get('email'))], limit=1)
            elif item_dict.get('login'):
                return self.sudo().search([('login', '=', item_dict.get('login'))], limit=1)
        return self.browse()
