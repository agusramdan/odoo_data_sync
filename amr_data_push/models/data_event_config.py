# -*- coding: utf-8 -*-

from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class InternalDataEventConfig(models.Model):
    _inherit = 'internal.data.event.config'
    _description = """
    """
    audiences = fields.Char("Audiences", help="Service service.endpoint code to update data")

    def get_push_fields(self):
        config = self
        field_names = set(self.env[self.model_id.model]._fields)
        if not config:
            return

        fields_exclude = config.get_fields_exclude()
        if fields_exclude:
            field_names -= set(fields_exclude)

        fields_include = config.get_fields_include()
        if fields_include:
            if fields_include[0] != '*':
                field_names &= set(fields_include)

        return list(field_names)
