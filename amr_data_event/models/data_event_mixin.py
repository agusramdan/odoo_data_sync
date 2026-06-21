
import logging

from odoo import models
from odoo.tools.safe_eval import safe_eval

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
    'user.delegation.'
    'whatsapp.'
)


def is_excluded(model_name):
    return model_name in EXCLUDE_MODELS or model_name.startswith(EXCLUDE_PREFIXES)


class DataEventMixin(models.AbstractModel):
    _inherit = 'base'

    def _is_excluded(self):
        return is_excluded(self._name)

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
            data ={
                'name': rec.display_name,
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'create',
                'changed_fields': "",
            }
            if 'company_id' in rec._fields and rec.company_id:
                data['company_id'] = rec.company_id.id
            event = AuditEvent.create(data)
            event.send_events()

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
        changed = {}
        if isinstance(vals,dict):
            changed = set(vals.keys()) - {'write_uid', 'write_date', '__last_update'}
        elif isinstance(vals, list):
            changed = set(vals) - {'write_uid', 'write_date', '__last_update'}
            _logger.debug("Vals is list %s . ",vals)
        elif isinstance(vals, set):
            changed = vals - {'write_uid', 'write_date', '__last_update'}
            _logger.debug("Vals is set %s . ", vals)
        fields_exclude = config.get_fields_exclude()
        if fields_exclude:
            changed -= set(fields_exclude)

        fields_include = config.get_fields_include()
        if fields_include:
            if fields_include[0] != '*':
                changed &= set(fields_include)

        if not changed:
            return

        filter_expr = config.filter_expr
        filter_expr = filter_expr and filter_expr.strip()

        if filter_expr:
            records = self.browse()

            for record in self:
                if safe_eval(filter_expr, {"record": record}):
                    records |= record
        else:
            records = self

        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in records:
            data = {
                'name': rec.display_name,
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'write',
                'changed_fields': ",".join(changed),
            }
            if 'company_id' in rec._fields and rec.company_id:
                data['company_id'] = rec.company_id.id
            event = AuditEvent.create(data)
            event.send_events()

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
            data = {
                'name': rec.display_name,
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'unlink',
                'changed_fields': "",
            }
            if 'company_id' in rec._fields and rec.company_id:
                data['company_id'] = rec.company_id.id
            event = AuditEvent.create(data)
            event.send_events()
