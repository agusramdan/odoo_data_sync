# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = [_name, 'internal.data.default.mixin']
