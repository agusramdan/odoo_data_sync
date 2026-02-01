# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.addons.amr_jsonrpc.utils import savepoint

import logging


_logger = logging.getLogger(__name__)


class InternalDataSync(models.Model):
    _inherit = 'external.server.sync'

    event_listener = fields.Boolean(default=True)
    strategy_ids = fields.One2many(
        'external.data.sync.strategy', 'server_sync_id'
    )
    last_data_event_id = fields.Many2one(
        'external.data.event', readonly=True,
        compute='_compute_last_data_event_id'
    )
    def _compute_last_data_event_id(self):
        for auth in self:
            auth.last_data_event_id = self.last_data_event_id.search(
                [('server_id', '=', auth.id)], order='id desc', limit=1
            )
    @savepoint(rethrow=True)
    def fetch_event_data_change(self):
        auth = self.ensure_one()
        last_data_event_id = auth.last_data_event_id
        last_id = last_data_event_id.external_odoo_id or 0
        external_data_company = self.env['external.data.company']
        with auth.create_remote_model('internal.data.event') as remote_model:
            data_list = remote_model.search_read([('id', '>', last_id)], order='id asc', limit=10)
            while data_list:
                for data in data_list:
                    last_id = data['id']
                    res_model = data['res_model']
                    res_id = data['res_id']
                    company = external_data_company.lookup_company(data.get('company_id'),auth)
                    strategies = auth.strategy_ids.filtered(lambda s: s.external_model == res_model)
                    if not strategies:
                        _logger.info("No strategy found for model %s, skipping data event ID %s", res_model, res_id)
                        continue
                    data_dict = {
                        key: value
                        for key, value in data.items()
                        if key in ['name', 'res_model', 'res_id', 'event_datetime', 'operation', 'changed_fields']
                    }
                    data_dict.update(
                        external_odoo_id=last_id,
                        server_id=auth.id,
                        strategy_ids=strategies.ids,
                    )
                    if company:
                        data_dict['company_id'] = int(company)
                    data_event = auth.env['external.data.event'].create(data_dict)
                    data_event.process()

                data_list = remote_model.search_read([('id', '>', last_id)], order='id asc', limit=10)


    def action_fetch_event_data_change(self):
        self.fetch_event_data_change()

    def cron_fetch_event_data_change(self):
        server_list = self or self.search([('event_listener','=',True)])

        for server in server_list:
            server.fetch_event_data_change()