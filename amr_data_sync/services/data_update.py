# -*- coding: utf-8 -*-

import logging

from odoo import api, models
from ..exceptions.api_exception import ValidationException
from werkzeug.exceptions import Unauthorized


_logger = logging.getLogger(__name__)


class DataUpdateService(models.AbstractModel):
    _name = "data.update.service"

    @classmethod
    def _required(cls, data, field_name, ):
        value = data.get(field_name)
        if not value:
            raise ValidationException("%s is required" % field_name)

        return value

    @api.model
    def get_token_strategy(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'amr_data_sync.date_update_security_option', 'secure_log'
        )

    @api.model
    def create_data_update(self, payload, ):
        data_update = self.env["external.data.update"]
        issuer = self._required(payload, 'issuer')
        external_model = self._required(payload, 'res_model')
        self._required(payload, 'res_id')
        self._required(payload, 'operation')
        self._required(payload, 'event_datetime')
        prepare_dict = data_update.prepare_data_update(payload)
        # server_sync = self.env["external.server.sync"].search([('base_url', '=', issuer)],limit=1)

        data = payload.get('data') or {}
        company_id = payload.get('company_id') or data.get('company_id')
        external_company = None
        if company_id and isinstance(company_id, list):
            company_id = company_id[0]
        if company_id:
            external_company = self.env["external.data.company"].search(
                [('server_sync_id.base_url', '=', issuer), ('external_id', '=', company_id)])
            if external_company.company_id:
                prepare_dict['company_id'] = external_company.company_id.id

        if external_company:
            strategy = self.env["external.data.sync.strategy"].search(
                [('external_model', '=', external_model),
                 ('server_sync_id.base_url', '=', issuer),
                 ('company_ids', '=', external_company.company_id.id)
                 ]
            )
            if not strategy:
                strategy = self.env["external.data.sync.strategy"].search(
                    [('external_model', '=', external_model),
                     ('server_sync_id.base_url', '=', issuer),
                     ('company_ids', '=', False)
                     ], limit=1
                )
        else:
            strategy = False
        if strategy:
            prepare_dict['strategy_id'] = strategy.id
            prepare_dict['state'] = 'accept'
        else:
            prepare_dict['strategy_id'] = False
            prepare_dict['state'] = 'error'
        accept = data_update.create(prepare_dict)
        return accept

    @api.model
    def data_update(self, payload, ):
        # self.env['ir.http'].check_scope("data_update.push")
        # get issuer from token
        issuer_accept = True
        token_strategy = self.get_token_strategy()
        if token_strategy == "not_secure":
            _logger.warning("Token Strategy not secure.")
        else:
            jwt_payload = self.env["ir.http"].get_jwt_payload()
            issuer = jwt_payload.get('azp')
            if issuer:
                payload['issuer'] = issuer
            else:
                issuer_accept = False

        if not issuer_accept and token_strategy == "secure":
            raise Unauthorized(description="Invalid issuer/azp token")

        accept = self.create_data_update(payload, )
        if issuer_accept and accept.state == 'accept':
            accept.dispatch_process()
            return {
                "data_accept": accept.id,
                "status": "accepted",
            }
        else:
            return {
                "data_accept": accept.id,
                "status": "error",
            }
