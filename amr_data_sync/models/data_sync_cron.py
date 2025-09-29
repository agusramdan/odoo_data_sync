# -*- coding: utf-8 -*-

import ast
import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import traceback
import logging
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ExternalDataSyncCron(models.Model):
    _name = 'external.data.sync.cron'
    _description = """Model strategy bagaimana object di synccron dari server external
    """
    sync_strategy_id = fields.Many2one(
        'external.data.sync.strategy',
        string='Parent Data Sync Strategy',
        delegate=True, ondelete='restrict', required=True
    )

    active = fields.Boolean(default=True)
    next_sync_datetime = fields.Datetime()
    last_sync_datetime = fields.Datetime()

    # @api.model_create_multi
    # @api.returns('self', lambda value: value.id)
    # def create(self, vals_list):
    #     for vals in vals_list:
    #         if 'server_sync_id' in vals and vals['server_sync_id']:
    #             server = self.server_sync_id.browse(vals['server_sync_id'])
    #             if not server:
    #                 raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
    #             vals['external_app_name'] = server.app_name
    #
    #     return super(ExternalDataSyncCron, self).create(vals_list)
    #
    # def write(self, vals):
    #     if 'server_sync_id' in vals and vals['server_sync_id']:
    #         server = self.server_sync_id.browse(vals['server_sync_id'])
    #         if not server:
    #             raise UserError(_("Server dengan ID %s tidak ditemukan") % vals['sync_strategy_id'])
    #         vals['external_app_name'] = server.app_name
    #
    #     return super(ExternalDataSyncCron, self).write(vals)

    def cron_sync_from_server(self):
        limit_time = fields.Datetime.now() + datetime.timedelta(minutes=30)
        data_sync_models = self.search([
            ('strategy', 'in', ['external_cud', 'external_cu', 'external_create']),
            '|', ('next_sync_datetime', '=', False), ('next_sync_datetime', '<=', fields.Datetime.now())
        ], order='next_sync_datetime asc')
        for data_sync in data_sync_models:
            last_sync_datetime = fields.Datetime.now()
            try:
                data_sync.sync_from_application_server()
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
