# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, api
from odoo.addons.base.models.ir_fields import exclude_ref_fields
from odoo.exceptions import UserError
from odoo.tools import image_process
import json
import logging
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartnerUsers(models.Model):
    _inherit = 'res.partner'

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
            domain = []
            if item_dict.get('email'):
                domain.append(('email', '=', item_dict.get('email')))
            elif item_dict.get('name'):
                domain.append(('name', '=', item_dict.get('name')))
            return self.sudo().search(domain, limit=1)
        return self.browse()
