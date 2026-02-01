# -*- coding: utf-8 -*-

from odoo.addons.amr_jsonrpc.utils import savepoint
from odoo import models, fields
import traceback
import logging

_logger = logging.getLogger(__name__)


class InternalDataSync(models.Model):
    _name = 'external.data.event'
    _description = "Internal data event yang akan assess oleh external app"
    _order = 'id desc'

    server_id = fields.Many2one(
        'external.server.sync', ondelete='set null'
    )
    strategy_ids = fields.Many2many('external.data.sync.strategy')
    data_ids = fields.Many2many('external.data.sync')
    external_odoo_id = fields.Integer('Id External')

    name = fields.Char()
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
        ('process', 'Process'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='pending', index=True)
    error_message = fields.Text()

    @savepoint
    def write_error(self, stack_trace):
        error_data = {
            'error_message': stack_trace,
            'state': 'error',

        }
        # if payload:
        #     error_data['payload_json'] = json.dumps(payload, default=date_utils.json_default)
        self.write(error_data)

    def process(self):
        try:
            # try with exception
            with self.env.cr.savepoint():
                data_ids = []
                item = {
                    'id': self.res_id,
                    'write_date': self.event_datetime,
                    'display_name': self.name,
                }
                for sync_strategy in self.strategy_ids:
                    if self.operation == 'unlink':
                        domain = [
                            ('external_odoo_id', '=', self.res_id),
                            ('sync_strategy_id', '=', sync_strategy.id)
                        ]
                        data = self.data_ids.search(domain)
                        data.write({'external_deleted': True, 'deleted_datetime': self.event_datetime})
                    else:
                        data = self.data_ids.data_from_external(
                            item, sync_strategy, create_when_not_found=True
                        )

                    data and data_ids.extend(data.ids)
                # for strategy in self.strategy_ids:
                #     strategy.process_data_event(self)
                # self.state = 'done'
                self.write({
                    'state': 'done',
                    'data_ids': [(6, 0, data_ids)]
                })
        except Exception:
            all_related_done = False
            # todo clear cache odoo
            self.write_error(traceback.format_exc())
