from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class DataShareMixin(models.AbstractModel):
    _name = 'internal.data.share.mixin'
    _description = """
    Model ini digunakan untuk pertukaran data transaksi atau master antara module dalam multi application database Odoo.
    Data master yang perlu ada statement persetujuan sebelum digunakan di module lain.
    """

    def share_data(self):
        AuditEvent = self.env['internal.data.event'].sudo()
        for rec in self:
            data = {
                'name': rec.display_name,
                'res_model': rec._name,
                'res_id': rec.id,
                'operation': 'share',
                'changed_fields': "",
            }
            if 'company_id' in self._fields:
                data['company_id'] = int(rec.company_id)
            AuditEvent.create(data)
