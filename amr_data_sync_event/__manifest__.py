# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

{
    'name': "Internal Data Sync by Event",
    'summary': """ 
    Internal Data Sync by Event
        """,
    'description': """
    """,
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "https://agus.ramdan.tech",
    'category': 'tools',
    'version': '13.0.0.0.2',
    'depends': ['base', 'mail','amr_jsonrpc', 'amr_data_sync'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/data_event_views.xml',
        'views/server_sync_views.xml',
        'views/menuitem.xml',
        'data/cron.xml',
    ],
}
