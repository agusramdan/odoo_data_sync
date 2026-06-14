# -*- coding: utf-8 -*-

from odoo import api, models
from ..exceptions.api_exception import ValidationException


class DataUpdateService(models.AbstractModel):
    _name = "data.update.service"

    @classmethod
    def _required(cls, data, field_name, ):
        value = data.get(field_name)
        if not value:
            raise ValidationException("%s is required" % field_name)

        return value

    @api.model
    def create_data_update(self, payload, ):
        data_update = self.env["external.data.update"]
        issuer=self._required(payload, 'issuer')
        self._required(payload, 'res_id')
        external_model = self._required(payload, 'res_model')
        self._required(payload, 'operation')
        self._required(payload, 'event_datetime')
        prepare_dict = data_update.prepare_data_update(payload)
        strategy = self.env["external.data.sync.strategy"].search(
            [('external_model','=',external_model),
             ('server_sync_id.base_url','=',issuer)]
        )
        if issuer:
            prepare_dict['strategy_id'] = strategy.id
        data = payload.get('data') or {}
        company_id = payload.get('company_id') or data.get('company_id')
        if company_id and isinstance(company_id,list):
            company_id = company_id[0]
        if company_id:
            external_company = self.env["external.data.company"].search([('server_sync_id','=',strategy.server_sync_id.id),('external_id','=',company_id)])
            if external_company.company_id:
                prepare_dict['company_id'] = external_company.company_id.id
        accept = data_update.create(prepare_dict)
        return accept

    @api.model
    def data_update(self, payload, ):
        # self.env['ir.http'].check_scope("data_update.push")

        message = self.create_data_update( payload, )
        message.dispatch_process()
        return {
            "data_accept": message.id,
            "status": "accepted",
        }
