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


class ResCurrency(models.Model):
    _name = 'res.currency'
    _inherit = [_name, 'internal.data.name.mixin']
