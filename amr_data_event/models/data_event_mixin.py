from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

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

    #
    'external.data.event',
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
    'antareja.',
    'notification.'
    'user.delegate.'
    'whatsapp.'
)


def is_excluded(model_name):
    return model_name in EXCLUDE_MODELS or model_name.startswith(EXCLUDE_PREFIXES)


class DataEventMixin(models.AbstractModel):
    _inherit = 'base'

    def _is_excluded(self):
        return is_excluded(self._name)

    # @api.model_create_multi
    # @api.returns('self', lambda value: value.id)
    # def create(self, vals_list):
    #     records = super(DataEventMixin, self).create(vals_list)
    #
    #     try:
    #         records and (self._is_excluded() or self._event_light_log_create(records))
    #     except Exception:
    #         _logger.exception("Audit create failed")
    #
    #     return records

    def modified(self, fnames, create=False, before=False):
        result = super(DataEventMixin, self).modified(fnames, create, before)
        if not self or before:
            return result
        if create:
            try:
                (self._is_excluded() or self._event_light_log_create(self))
            except Exception:
                _logger.exception("Audit create failed")
        else:
            try:
                self._is_excluded() or self._event_light_log_modified(fnames)
            except Exception:
                _logger.exception("Audit modified failed")
        return result

    def unlink(self):
        try:
            self and (self._is_excluded() or self._event_light_log_unlink())
        except Exception:
            _logger.exception("Audit unlink failed")

        return super(DataEventMixin, self).unlink()

    def _event_light_log_create(self, record):
        # safety
        if self.env.context.get('skip_data_event'):
            return

        # exclude audit models
        if self._name in {
            'internal.data.event',
            'internal.data.event.config',
        }:
            return

        config = self.env['internal.data.event.config'].sudo().get_config_create(self._name)

        if not config:
            return

        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in record:
            AuditEvent.create({
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'write',
                'changed_fields': "",
            })

    def _event_light_log_modified(self, vals):
        # safety
        if self.env.context.get('skip_data_event'):
            return

        # exclude audit models
        if self._name in {
            'internal.data.event',
            'internal.data.event.config',
        }:
            return

        config = self.env['internal.data.event.config'].sudo().get_config_write(self._name)

        if not config:
            return

        changed = set(vals.keys()) - {'write_uid', 'write_date', '__last_update'}

        fields_exclude = config.get_fields_exclude()
        if fields_exclude:
            changed -= set(fields_exclude)

        fields_include = config.get_fields_include()
        if fields_include:
            if fields_include[0] != '*':
                changed &= set(fields_include)

        if not changed:
            return

        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in self:
            AuditEvent.create({
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'write',
                'changed_fields': ",".join(changed),
            })

    def _event_light_log_unlink(self):
        # safety
        if self.env.context.get('skip_data_event'):
            return

        # exclude audit models
        if self._name in {
            'internal.data.event',
            'internal.data.event.config',
        }:
            return

        config = self.env['internal.data.event.config'].sudo().get_config_unlink(self._name)

        if not config:
            return

        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in self:
            AuditEvent.create({
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'write',
                'changed_fields': "",
            })
