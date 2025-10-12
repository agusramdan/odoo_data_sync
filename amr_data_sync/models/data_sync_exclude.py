# -*- coding: utf-8 -*-

from odoo import models, fields, _
import logging

_logger = logging.getLogger(__name__)


class ExternalDataSyncExclude(models.Model):
    _name = 'external.data.sync.exclude'
    _description = """
Model untuk menyimpan konfigurasi exclude field atau model
    """

    active = fields.Boolean(default=True)
    exclude = fields.Selection([
        ('fields', 'Exclude Fields In Model'),
        ('model', 'Exclude Model'),
        ('all_fields', 'Exclude All Field in Model'),
    ], default='fields')
    model = fields.Char(required=True)
    fields = fields.Char()

    def get_exclude_all_fields(self):
        env = self.env
        exclude_fields = []
        for exclude in self.search([('exclude', '=', 'all_fields'), ('active', '=', True)]):
            try:
                if exclude.model in env:
                    model = env[exclude.model]
                    if model._abstract:
                        exclude_fields.extend(model._fields.keys())
            except Exception as e:
                _logger.error(f"Error evaluating exclude fields for model: {e}")
                continue
        return exclude_fields

    def get_exclude_fields(self, model_name):
        env = self.env
        exclude_fields = []
        for exclude in self.search([('exclude', '=', 'all_fields'), ('active', '=', True)]):
            try:
                if exclude.model in env:
                    exclude_fields.extend(env[exclude.model]._fields.keys())
            except Exception as e:
                _logger.error(f"Error evaluating exclude fields for model: {e}")
                continue
        for exclude in self.search([('exclude', '=', 'fields'), ('model', '=', model_name), ('active', '=', True)]):
            try:
                if exclude.model in env and exclude.fields:
                    exclude_fields.extend(exclude.fields.sprit(','))
            except Exception as e:
                _logger.error(f"Error evaluating exclude fields for model: {e}")
                continue
        return list(set(exclude_fields))

    def is_exclude_model(self, model_name):
        return bool(
            self.search([('exclude', '=', 'model'), ('model', '=', model_name), ('active', '=', True)], limit=1))
