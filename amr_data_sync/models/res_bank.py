# -*- coding: utf-8 -*-

from odoo import models
import logging

_logger = logging.getLogger(__name__)


class Bank(models.Model):
    _name = 'res.bank'
    _inherit = [_name, 'internal.data.name.mixin']

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
            if item_dict.get('name'):
                domain.append(('name', '=', item_dict.get('name')))
                return self.sudo().search(domain, limit=1)
        return self.browse()
