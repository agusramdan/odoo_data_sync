# -*- coding: utf-8 -*-

import datetime
from odoo import models, fields, api, _
import traceback
import logging

_logger = logging.getLogger(__name__)


class ExternalDataSyncCron(models.Model):
    _name = 'external.data.sync.cron'
    _description = """Model strategy bagaimana object di sync cron dari server external
    """
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        string='Parent Data Sync Strategy',
        delegate=True, ondelete='restrict', required=True
    )

    active = fields.Boolean(default=True)
    # sync_cron = fields.Boolean(default=True)
    next_sync_datetime = fields.Datetime()
    last_sync_datetime = fields.Datetime()

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        return super(ExternalDataSyncCron, self.with_context(__from_sync_cron=True)).create(vals_list)

    def write(self, vals):
        result = super(ExternalDataSyncCron, self).write(vals)
        if self._context.get('__from_sync_cron'):
            return result
        if 'active' in vals:
            for rec in self.with_context(__from_sync_cron=True):
                if rec.sync_strategy_id and rec.active != rec.sync_strategy_id.sync_cron:
                    rec.sync_strategy_id.write({
                        'sync_cron': rec.active
                    })
        return result

    def action_sync_now(self):
        self.sync_strategy_id.action_sync_now()

    def cron_sync_from_server(self):
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=30)
        data_sync_models = self or self.search([
            ('strategy', 'in', ['external_cud', 'external_cu', 'external_create']),
            '|', ('next_sync_datetime', '=', False), ('next_sync_datetime', '<=', fields.Datetime.now())
        ], order='next_sync_datetime asc')
        for data_sync in data_sync_models:
            last_sync_datetime = fields.Datetime.now()
            try:
                data_sync.sync_strategy_id.sync_from_application_server()
            except Exception as e:
                _logger.error(
                    "Error sync from server %s , model %s : %s",
                    data_sync.external_app_name,
                    data_sync.external_model,
                    traceback.format_exc()
                )
            finally:
                data_sync.write({
                    'last_sync_datetime': last_sync_datetime,
                    'next_sync_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
                })

            if fields.Datetime.now() > limit_time:
                break
