 # -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.exceptions import UserError

class LogisflooProduct(models.Model):
    _inherit = 'product.template'
    
#    total_with_margin = fields.Float(compute='_get_total_with_margin', store=False, string="Total Sales Price with Margin")
    total_with_margin = fields.Float(compute='_compute_cost', store=False, string="Total Sales Price with Margin")
    reference_price = fields.Float(string='Invoice Price')
    producer = fields.Char(string="Producer")
    default_code = fields.Char(store=True)
    internal_ref = fields.Char(string="Internal Reference")

    _defaults = {
        'type' : 'product',
    }

    @api.one
    def _get_total_with_margin(self):
        margin_amount = self.standard_price * 0.05
        self.total_with_margin = self.standard_price + margin_amount

    def _get_main_supplier_info(self):
        return self.seller_ids.sorted(key=lambda seller: seller.date_start, reverse=True)

    @api.one
    @api.depends('seller_ids')
    def _compute_cost(self):
        suppliers = self._get_main_supplier_info()
        if(len(suppliers) > 0):
#            self.suggested_price = (suppliers[0].price * (1-suppliers[0]/100) * self.uom_po_id.factor)* (1 + suppliers[0].product_tmpl_id.categ_id.profit_margin / 100)
            discounted_sell_unit_price = suppliers[0].price * self.uom_po_id.factor * (1-suppliers[0].discount/100)
            self.total_with_margin = discounted_sell_unit_price 
            self.total_with_margin = self.total_with_margin + self.supplier_taxes_id._compute_amount(discounted_sell_unit_price, discounted_sell_unit_price) 
            self.total_with_margin = self.total_with_margin * (1.05)

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
    
class product_supplierinfo(models.Model):  
    _inherit = 'product.supplierinfo'
    
    discount = fields.Float(string='Discount')