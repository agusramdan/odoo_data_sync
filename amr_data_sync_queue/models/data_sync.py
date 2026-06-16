# -*- coding: utf-8 -*-

import datetime
import json
import logging
import traceback
from collections import defaultdict

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools import date_utils
from psycopg2.errors import SerializationFailure
from odoo.addons.queue_job.exception import RetryableJobError
from psycopg2._psycopg import TransactionRollbackError

_logger = logging.getLogger(__name__)


class ExternalDataSync(models.Model):
    _inherit = 'external.data.sync'

    on_queue = fields.Boolean(default=False, )

    def process_with_handel_error(self):
        try:
            with self.env.cr.savepoint():
                self.process_data()

        except SerializationFailure:
            raise RetryableJobError("Concurrent update detected")
        except Exception:
            _logger.exception("Error rec %s", self)
            self.write_error_safe({
                'error_info': traceback.format_exc(),
                'state': 'error',
                'last_error': fields.Datetime.now(),
                'next_processing_datetime': fields.Datetime.now() + datetime.timedelta(hours=1),
            })

    def write_done_internal_odoo(self, internal_odoo, payload=None):
        result = super().write_done_internal_odoo(internal_odoo, payload=payload)
        self.write({'on_queue': False})
        return result

    def write_error_safe(self, error_data, using_pool=False):
        error_data['on_queue'] = False
        super().write_error_safe(error_data, using_pool=using_pool)

    def dispatch_process(self, run_immediate=False):
        self.write({'on_queue': True, 'state': 'process'})
        self.with_delay().process_with_handel_error()

    def cron_process_data(self, limit=1000):
        records = self.search(
            [('on_queue', '=', False), ('need_get_data_json', '=', True)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for rec in records:
            rec.dispatch_process()

        records = self.search(
            [('on_queue', '=', False), ('state', '!=', 'done'),
             '|',
             ('next_processing_datetime', '<=', fields.Datetime.now()),
             ('next_processing_datetime', '=', False)],
            limit=limit, order='next_processing_datetime asc,last_processing_datetime asc, id '
        )
        for rec in records:
            rec.dispatch_process()
