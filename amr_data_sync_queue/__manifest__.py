# -*- coding: utf-8 -*-
{
    'name': "External Data Sync Process Queue ",
    'summary': "Replace processing using queue",
    'description': " ",
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "http://agus.ramdan.tech",
    'category': 'API',
    'version': '13.0.0.0.0',
    'depends': ['base', 'amr_data_sync', 'queue_job'],
    # always loaded
    'data': [
        "views/data_sync_views.xml",
    ],
}
