# -*- coding: utf-8 -*-

from odoo import api, models


class TokenValidatorService(models.AbstractModel):
    _name = 'token.validator.service'

    @api.model
    def validate_token(self, token_str):
        return None
