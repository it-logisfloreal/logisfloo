        # -*- coding: utf-8 -*-
{
    'name': "Logis-Floréal Base Module",

    'summary': """
		Module that customize the base module and contains some python tools
		Inspired from Beescoop - Cellule IT https://github.com/beescoop/Obeesdoo
     """,

    'description': """
    """,

    'author': "Logis-Floréal - Cellule IT",
    'website': "https://github.com/logisfloo",

    'category': 'Logisfloo',
    'version': '0.1',

    'depends': [
        'stock',
        'sale',
        'point_of_sale',
        'mail',
        'account',
        'account_accountant',
        'website', 
        'purchase', 
        'product',
        'board', 
        'pos_price_to_weight', 
        'report',
        'beesdoo_coda',
    ],

    'data': [
        'security/logisfloo_security.xml',
        'data/default_values.xml',
        'data/email.xml',
        'data/sequence_definition.xml',
        'views/partner.xml',
        'views/product.xml',
        'views/report_receipt.xml',
        'views/logisfloo_pos.xml',
    ],
    'qweb': [
    'static/src/xml/pos_extensions.xml',
        ],
}
