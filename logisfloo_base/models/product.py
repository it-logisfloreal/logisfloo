 # -*- coding: utf-8 -*-
from openerp import models, fields, api

class Product(models.Model):

    _inherit = 'product.template'
    
    total_with_margin = fields.Float(compute='_get_total_with_margin', store=False, string="Total Sales Price with Margin")
    reference_price = fields.Float(string='Invoice Price')
    producer = fields.Char(string="Producer")
    
    def _get_total_with_margin(self):
        margin_amount = self.standard_price * 0.05
        self.total_with_margin = self.standard_price + margin_amount
