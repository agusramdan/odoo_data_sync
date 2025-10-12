# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = {}
        if isinstance(item, list):
            if len(item) > 0:
                item_dict['id'] = item[0]
            if len(item) > 1:
                item_dict['name'] = item[1]
        elif isinstance(item, dict):
            item_dict = item
        elif isinstance(item, str):
            item_dict['name'] = item

        if item_dict:
            name = item_dict.get('name')
            if name:
                return self.sudo().search([('name', '=', name)], limit=1)

        return self.browse()
