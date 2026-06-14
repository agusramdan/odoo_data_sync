# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools import date_utils


_logger = logging.getLogger(__name__)


class ExternalDataUpdate(models.Model):
    _inherit = 'external.data.update'

    def dispatch_process(self,run_immediate=False):
        self.with_delay().process_data()
