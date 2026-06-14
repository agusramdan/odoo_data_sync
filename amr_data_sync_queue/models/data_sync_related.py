# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, SUPERUSER_ID
from odoo.tools import date_utils


_logger = logging.getLogger(__name__)


class ExternalDataSyncRelated(models.Model):
    _inherit = 'external.data.sync.related'

    on_queue = fields.Boolean(default=False, )

    def process_data(self):
        try:
           super().process_data()
        finally:
            self.write({'on_queue': False})

    def write_error_safe(self,error_data,using_pool=False):
        error_data['on_queue']=False
        super().write_error_safe(error_data,using_pool=using_pool)

    def dispatch_process(self,run_immediate=False):
        self.write({'on_queue': True,'state':'process'})
        self.with_delay().process_data()

