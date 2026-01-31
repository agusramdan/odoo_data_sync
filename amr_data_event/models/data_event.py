# -*- coding: utf-8 -*-

import ast
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import json
import traceback
import logging

_logger = logging.getLogger(__name__)


class InternalDataSync(models.Model):
    _name = 'internal.data.event'
    _description = "Internal data event yang akan assess oleh external app"
    name = fields.Char("Display Name")
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    company_id = fields.Many2one('res.company')
    event_datetime = fields.Datetime(default=fields.Datetime.now)
    operation = fields.Selection([
        ('create', 'Create'),
        ('write', 'Write'),
        ('unlink', 'Delete'),
    ], required=True)
    changed_fields = fields.Char()
    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('error', 'Error'),
    ], default='sent', index=True)
    error_message = fields.Text()

    def send_events(self):
        """
        overide this when using message broker to send external
        """
        for rec in self:
            if rec.state in ['pending','error']:
                rec.state='sent'
