# -*- coding: utf-8 -*-
{
    'name': "Application Addons",
    'summary': """Application Addons""",
    'description': """
Application Addons
Ini adalah anti pola dari odoo.
odoo berharap 1 applikasi untuk semua kebutuhan.
Tapi dalam metode ini multi applikasi odoo untuk kebutuhan perusahan 

Model ini adalah titik tengah antara applikasi monolitik 

Untuk berhubungan dengan resource microservice external mengunakan rest 
sedangkan untuk applikasi odoo mengunakan jsonrpc 


""",
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.agus.ramdan.tect",
    'category': 'Tool',
    'version': '13.0.0.0.0',
    'depends': ['base'],
    # always loaded
    'data': [
        "views/application_resource_views.xml",
        "views/application_auth_views.xml",
        "views/application_resource_views.xml",
    ],
}
