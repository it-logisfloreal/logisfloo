        # -*- coding: utf-8 -*-
{
    'name': "Logis-Floréal Base Module",

    'summary': """
		Module that customize the Beesdoo base module and contains some python tools
     """,

    'description': """
    """,

    'author': "Logis-Floréal - Cellule IT",
    'website': "https://github.com/logisfloo",

    'category': 'Project Management',
    'version': '0.1',

    'depends': ['beesdoo_base', 'beesdoo_pos'],

    'data': [
    'data/default_values.xml',
    'views/partner.xml',
    'views/product.xml',
    'views/report_receipt.xml',
    'views/logisfloo_pos.xml',
    ],
    'qweb': [
    'static/src/xml/pos_extensions.xml',
        ],
}
