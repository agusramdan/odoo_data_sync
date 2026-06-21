# -*- coding: utf-8 -*-
{
    'name': "External Data Sync ",
    'summary': "Store information data from external system",
    'description': "Store information data from external system",
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "http://agus.ramdan.tech",
    'category': 'API',
    'version': '13.0.3.0.0',
    'depends': ['base', 'mail', 'amr_resource', 'amr_service_client'],
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
        'views/data_update_views.xml',
        'views/res_config_settings_views.xml',
        'views/menuitem.xml',

        'data/cron.xml',
    ],
}
