# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

{
    'name': "Internal Data Event",
    'summary': "Internal Data Event",
    'description': "Internal Data Event",
    'author': "Agus Muhammad Ramdan",
    "license": "AGPL-3",
    'website': "https://agus.ramdan.tech",
    'category': 'tools',
    'version': '13.0.0.0.5',
    'depends': ['base'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/data_event_config_views.xml',
        'views/data_event_views.xml',
        'views/menuitem.xml',
    ],
}
