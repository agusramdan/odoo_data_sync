# -*- coding: utf-8 -*-

import json
import traceback
import logging

from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class ExternalDataUpdate(models.Model):
    _name = 'external.data.update'
    _description = "Accept Data From external"
    _order = 'id desc'
    name = fields.Char()
    data_id = fields.Many2one('external.data.sync')
    company_id = fields.Many2one('res.company')
    strategy_id = fields.Many2one('external.data.sync.strategy')
    res_model = fields.Char('Model External', required=True, index=True,)
    res_id = fields.Integer('ID External', required=True, index=True)
    event_datetime = fields.Datetime(default=fields.Datetime.now)
    operation = fields.Selection([
        ('upsert', 'Update Insert'),
        ('unlink', 'Delete'),
    ], required=True)
    state = fields.Selection([
        ('accept', 'Accept'),
        ('process', 'Process'),
        ('error', 'Error'),
        ('done', 'Done'),
    ], default='accept', index=True, readonly=True)
    error_message = fields.Text()
    raw_payload=fields.Text()
    data_payload = fields.Text()

    def action_process(self):
        self.ensure_one()
        self.process_data()


    @api.model
    def prepare_data_update(self, payload):
        raw_payload = json.dumps(payload)
        payload = dict(payload)

        data = payload.get('data') or {}
        display_name = payload.get('display_name') or data.get('display_name')  or  payload.get('name') or data.get('display_name')
        res_id = payload.get('res_id') or data.get('id')
        res_model =  payload.get('res_model')
        operation = payload.get('operation')
        event_datetime = payload.get('event_datetime')
        if operation != "unlink":
            operation='upsert'
        data['id']=res_id
        data['display_name'] =display_name
        return {
            "name": display_name,
            "res_id": res_id,
            "res_model": res_model,
            "raw_payload": raw_payload,
            "operation": operation,
            "event_datetime":event_datetime,
            "data_payload": json.dumps(data)
        }

    def dispatch_process(self):
        self.process_data()

    def process_data(self):
        try:
            # try with exception
            with self.env.cr.savepoint():
                item = json.loads(self.data_payload)
                if self.operation == 'unlink':
                    domain = [
                        ('external_odoo_id', '=', self.res_id),
                        ('sync_strategy_id', '=', self.strategy_id.id)
                    ]
                    data = self.data_id.search(domain)
                    update = {'external_deleted': True, 'deleted_datetime': self.event_datetime}
                    if self.company_id:
                        update['company_id'] = self.company_id.id
                    data.write(update)
                else:
                    data = self.data_id.data_from_external(
                        item, self.strategy_id, create_when_not_found=True, need_get_data_json=False
                    )
                    # update company ensure same
                    if data and self.company_id:
                        data.write({'company_id', self.company_id.id})
                    _logger.info("Without Company %s .",data)
                data.dispatch_process()
                self.write({
                    'state': 'done',
                    'data_id': data.id,
                    'error_message': False
                })
        except Exception:
            self.write({'error_message':traceback.format_exc()})
