 # -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.exceptions import UserError

class LogisflooProduct(models.Model):
    _inherit = 'product.template'
    
    total_with_margin = fields.Float(compute='_get_total_with_margin', store=False, string="Total Sales Price with Margin")
    reference_price = fields.Float(string='Invoice Price')
    producer = fields.Char(string="Producer")
    
    @api.one
    def _get_total_with_margin(self):
        margin_amount = self.standard_price * 0.05
        self.total_with_margin = self.standard_price + margin_amount

class LogisflooProductCategory(models.Model):  
    _inherit = "product.category"

    profit_margin = fields.Float(default = '5.0', string = "Product Margin [%]")

    @api.one
    @api.constrains('profit_margin')
    def _check_margin(self):
        if (self.profit_margin < 0.0):
            raise UserError(_('Percentages for Profit Margin must > 0.'))


class LogisflooUOMCateg(models.Model):  
    _inherit = 'product.uom.categ'
    
    type = fields.Selection([('unit','Unit'),
                              ('weight','Weight'),
                              ('volume','Volume'),
                              ('time','Time'),
                              ('distance','Distance'),
                              ('surface','Surface'),
                              ('other','Other')],string='Category type',default='unit')