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

    def _check_credentials(self, password):
        try:
            return super(ResUsers, self)._check_credentials(password)
        except AccessDenied:
            res = self.sync_token_ids.sudo().search([('user_id', '=', self.env.uid), ('token', '=', password)])
            if not res:
                raise
