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


class InternalData(models.AbstractModel):
    _name = 'internal.data.mixin'

    @api.model
    def convert_for_lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = {}
        if isinstance(item, int):
            item_dict['id'] = item
        elif isinstance(item, list):
            if len(item) > 0:
                item_dict['id'] = item[0]
            if len(item) > 1:
                item_dict['name'] = item[1]
        elif isinstance(item, dict):
            item_dict = item

        return item_dict

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = self.convert_for_lookup_internal_from_external_data(item, **kwargs)
        if item_dict:
            if item_dict.get('id') == 1:
                return self.sudo().browse(item_dict.get('id'))
        return self.browse()
