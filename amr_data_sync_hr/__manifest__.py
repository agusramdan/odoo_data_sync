# -*- coding: utf-8 -*-
{
    'name': "External Data Sync HR ",
    'summary': "Store information data from external system",
    'description': "",
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "http://agus.ramdan.tech",
    'category': 'API',
    'version': '13.0.0.1.1',
    'depends': ['base', 'hr', 'amr_data_sync', 'amr_service_client'],
    # always loaded
    'data': [
        'data/external_server_sync_data.xml',
        'data/hr_department_data.xml',
        'data/hr_job_data.xml',
        'data/hr_employee_data.xml',
    ],
}
