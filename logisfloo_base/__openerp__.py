        # -*- coding: utf-8 -*-
{
    'name': "Logis-Floréal Base Module",

    'summary': """
		Module that customizes the base module and contains some python tools
		Inspired from Beescoop - Cellule IT https://github.com/beescoop/Obeesdoo
     """,

    'description': """
    """,

    'author': "Logis-Floréal - Cellule IT",
    'website': "https://github.com/logisfloo",

    'category': 'Logisfloo',
    'version': '1.6.8', 

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
        'security/ir.model.access.csv',
        'data/default_values.xml',
        'data/email.xml',
        'data/data_updates.xml',
        'views/assets.xml',
        'views/partner.xml',
        'views/product.xml',
        'views/report_receipt.xml',
        'views/logisfloo_pos.xml',
        'views/purchase.xml',
        'views/stock.xml',
        'views/account.xml',
        'views/poexpense.xml',
    ],
    'qweb': [
    'static/src/xml/pos_extensions.xml',
        ],
}
