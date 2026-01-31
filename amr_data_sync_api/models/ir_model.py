# -*- coding: utf-8 -*-

from odoo import api, models

EXCLUDE_MODELS = {
    # Technical
    'ir.model',
    'ir.model.fields',
    'ir.cron',
    'ir.ui.view',
    'ir.actions.act_window',

    # Security
    'res.users',
    'res.groups',
    'res.company',
    'res.config.settings',
    'user.delegate',

    # Messaging
    'mail.message',
    'mail.followers',
    'mail.activity',
    'send_message.email',
    'api.call.retry',
}

EXCLUDE_PREFIXES = (
    'ir.',
    'bus.',
    'base.',
    'mail.',
    'web.',
    'internal.data.',
    'external.data.',
    'application.',
    'approval.',
    'notification.'
)


class IrModel(models.Model):
    _inherit = 'ir.model'

    def excluded_read_sync_api(self):
        return self.model in EXCLUDE_MODELS or self.model.startswith(EXCLUDE_PREFIXES)

    @api.model
    def is_read_sync_api(self):
        return True

    @api.model
    def sudo_read_sync_api(self):
        return False
