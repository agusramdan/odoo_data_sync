# -*- coding: utf-8 -*-
{
    'name': "External Data Event Process Queue",
    'summary': "Replace processing using queue push to other system",
    'description': " ",
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "http://agus.ramdan.tech",
    'category': 'API',
    'version': '13.0.0.0.1',
    'depends': ['base', 'amr_data_event', 'queue_job', 'amr_service_client'],
    # always loaded
    'data': [
        'views/data_event_config_views.xml',
        'views/data_event_views.xml',
    ],
}
