# -*- coding: utf-8 -*-

import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import date_utils

_logger = logging.getLogger(__name__)


class InternalDataSync(models.Model):
    _inherit = 'internal.data.event'

    push_payload = fields.Text()
    audiences = fields.Char("Audiences")

    def prepare_payload(self):
        issuer= self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        name = self.name
        res_model = self.res_model
        res_id = self.res_id
        company_id = self.company_id
        event_datetime = self.event_datetime
        operation = self.operation
        config = self.env['internal.data.event.config'].sudo().get_config_write(res_model)
        payload = {
            'name': name,
            'issuer':issuer,
            'res_model' : res_model,
            'res_id':res_id,
            'event_datetime':event_datetime,
            'operation':operation,
        }
        if company_id:
            payload['company_id'] = company_id.id
        data = {'id':res_id}
        if operation != 'unlink':
            data_rec = self.env[res_model].sudo().with_context(__read_data_for_sync_external_application=True, active_test=False).browse(res_id)
            field_names=config.get_push_fields()
            data = data_rec.read(fields=field_names)[0]
        payload['data']=data
        self.write({
            'audiences': config.audiences,
            'push_payload':json.dumps(payload, default=date_utils.json_default)
        })

    def action_prepare_payload(self):
        self.prepare_payload()

    def action_dispatch_audiences(self):
        self.dispatch_audiences()

    def dispatch_audiences(self):
        self.prepare_payload()
        audiences = self.audiences
        if audiences:
            audiences_list = audiences.split(',')
            for audience in audiences_list:
                self.dispatch_audience(audience)

    def dispatch_audience(self,audience):
        pass

    def send_events(self):
        """
        overide this when using message broker to send external
        """
        for rec in self:
            if rec.state in ['pending','error']:
                rec.dispatch_audiences()
                rec.state='sent'
