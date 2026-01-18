# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, api
from odoo.addons.base.models.ir_fields import exclude_ref_fields
from odoo.exceptions import UserError
from odoo.tools import image_process
from ..tools.utils import convert_from_external_data
import json
import logging
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class InternalDataNameMixin(models.AbstractModel):
    _name = 'internal.data.name.mixin'

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = convert_from_external_data(item)
        if item_dict:
            domain = []
            if item_dict.get('name'):
                domain.append(('name', '=', item_dict.get('name')))
                return self.search(domain, limit=1)
            if item_dict.get('display_name'):
                domain.append(('name', '=', item_dict.get('display_name')))
                return self.search(domain, limit=1)

        if hasattr(super(), 'lookup_internal_from_external_data'):
            return super().lookup_internal_from_external_data(item, **kwargs)
        return self.browse()


class InternalDataDefaultMixin(models.AbstractModel):
    _name = 'internal.data.default.mixin'

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_data = convert_from_external_data(item)
        external_id = item_data.get('id')
        sync_strategy = kwargs.get('sync_strategy')
        result = self.browse()
        if sync_strategy:
            ExternalDataSync = self.env['external.data.sync']
            data = ExternalDataSync.search([
                ('external_id', '=', external_id),
                ('sync_strategy_id', '=', sync_strategy.id)
            ], limit=1)
            if data:
                return data.get_internal_object()
            if sync_strategy.internal_id_same_as_external and self._name == sync_strategy.internal_model:
                external_id = sync_strategy.get_internal_id_same_as_external(item)
                result = self.search([('id', '=', external_id)], limit=1)

        if result:
            return result

        if hasattr(super(), 'lookup_internal_from_external_data'):
            return super().lookup_internal_from_external_data(item, **kwargs)
        return self.browse()


class InternalData(models.AbstractModel):
    _name = 'internal.data.mixin'

    @api.model
    def convert_for_lookup_internal_from_external_data(self, item, **kwargs):
        return convert_from_external_data(item)

    def lookup_internal_from_external_data(self, item, **kwargs):
        item_dict = self.convert_for_lookup_internal_from_external_data(item, **kwargs)
        if item_dict:
            if item_dict.get('id') == 1:
                return self.sudo().browse(item_dict.get('id'))
        return self.browse()
