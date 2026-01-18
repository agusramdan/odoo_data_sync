# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResourceCalendar(models.Model):
    _name = "resource.calendar"
    _inherit = [_name, 'internal.data.name.mixin']


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = [_name, 'internal.data.default.mixin']
