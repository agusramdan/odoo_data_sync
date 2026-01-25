# -*- coding: utf-8 -*-

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ApplicationResource(models.Model):
    _name = 'application.resource'
    _description = """Application Resource Server
Resource Server

Tugas utamanya: menyimpan dan menyediakan resource / data / API yang dilindungi.
Yang dilakukan:

- Menerima request dengan Authorization: Bearer <token>
- Melakukan validasi token (JWT / introspection ke Auth Server)
- Mengecek scope / role

Mengizinkan atau menolak akses resource    
    """

    active = fields.Boolean(default=True)
    name = fields.Char('Name')
    description = fields.Char()
    endpoint = fields.Char()
    application_auth_ids = fields.One2many(
        'application.auth', 'application_resource_id',
        help="""Dafter autetikasi yang bisa dilakukan pada server"""
    )
    application_path_ids = fields.One2many(
        'application.path', 'application_resource_id',
        readonly=True
    )
