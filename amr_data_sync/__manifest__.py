# -*- coding: utf-8 -*-
{
    'name': "External Data Sync ",
    'summary': """
        Store infomation data from external system
        """,
    'description': """
    """,
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "http://agus.ramdan.tech",
    'category': 'API',
    'version': '13.0.2.2.1',
    'depends': ['base', 'mail', 'amr_jsonrpc'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/data_sync_views.xml',
        'views/server_sync_views.xml',
        'views/data_company_views.xml',
        'views/data_sync_related_views.xml',
        'views/data_sync_exclude_views.xml',
        'views/data_sync_strategy_views.xml',
        'views/data_sync_cron_views.xml',
        'views/data_lookup_views.xml',
        'views/data_mapping_views.xml',
        'views/menuitem.xml',
        'data/cron.xml',
    ],
}
