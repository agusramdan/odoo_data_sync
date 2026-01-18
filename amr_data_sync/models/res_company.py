# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _name = 'res.company'
    _inherit = [_name, 'internal.data.name.mixin']
