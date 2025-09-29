# -*- coding: utf-8 -*-
{
    'name': "External Data Sync ",
    'summary': """
        Store infomation data from external system
        """,
    'description': """
    """,
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",
    'category': 'API',
    'version': '13.0.0.0.0',
    'depends': ['base',],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/data_sync_views.xml',
        'views/server_sync_views.xml',
        'views/data_sync_exclude_views.xml',
        'views/data_sync_strategy_views.xml',
        'views/data_lookup_views.xml',
        'views/res_user_view.xml',
        'views/ir_model_view.xml',
        'views/menuitem.xml',
        'data/cron.xml',
    ],
}
