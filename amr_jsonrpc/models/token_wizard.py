# models/token_wizard.py
from odoo import models, fields, _
from odoo.exceptions import UserError
import requests
from datetime import datetime, timedelta


class GetTokenWizard(models.TransientModel):
    _name = 'amr.get.token.wizard'
    _description = 'OAuth Get Token Wizard'

    url = fields.Char(required=True)
    username = fields.Char(required=True)
    password = fields.Char(required=True)

    access_token = fields.Text(readonly=True)
    refresh_token = fields.Text(readonly=True)
    expires_at = fields.Datetime(readonly=True)
    message = fields.Text(readonly=True)

    def action_get_token(self):
        self.ensure_one()

        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": "CLIENT_ID",
            "client_secret": "CLIENT_SECRET"
        }

        try:
            response = requests.post(self.url, data=payload, timeout=10)
        except Exception as e:
            raise UserError(_("Connection error: %s") % e)

        if response.status_code != 200:
            raise UserError(_("Auth failed: %s") % response.text)

        data = response.json()

        expires_at = False
        if data.get('expires_in'):
            expires_at = datetime.utcnow() + timedelta(
                seconds=int(data['expires_in'])
            )

        self.write({
            'access_token': data.get('access_token'),
            'refresh_token': data.get('refresh_token'),
            'expires_at': expires_at,
            'message': 'Token berhasil didapatkan'
        })

        # Simpan permanen (recommended)
        self._save_token(data, expires_at)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _save_token(self, data, expires_at):
        action_id = self.env.context.get('action_id')
        action_model = self.env.context.get('action_model')
        action = self.env[action_model].browse(action_id)
        action.write({
            "username": self.username,
            "refresh_endpoint": self.url,
            "password": '',
            'access_token': data.get('access_token'),
            'refresh_token': data.get('refresh_token'),
            'expires_at': expires_at
        })
        # ICP = self.env['ir.config_parameter'].sudo()
        # ICP.set_param('amr.oauth.access_token', data.get('access_token'))
        # ICP.set_param('amr.oauth.refresh_token', data.get('refresh_token'))
        # ICP.set_param('amr.oauth.expires_at', expires_at)
