 # -*- coding: utf-8 -*-
from openerp import models, fields, api

class Prodcut(models.Model):

    _inherit = 'product.template'
    
    total_with_margin = fields.Float(compute='_get_total_with_margin', store=True, string="Total Sales Price with Margin")
    
    def _get_total_with_margin(self):
        margin_amount = self.list_price * 0.05
        self.total_with_vat = self.list_price + margin_amount
    
