 # -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)

class LogisflooProduct(models.Model):
    _inherit = 'product.template'
    
    total_with_margin = fields.Float(compute='_compute_cost', store=False, string="Total Sales Price with Margin")
    reference_price = fields.Float(string='Invoice Price')
    producer = fields.Char(string="Producer")
    default_code = fields.Char(store=True)
    internal_ref = fields.Char(string="Internal Reference")
    pos_categ_id = fields.Many2one('pos.category','Point of Sale Category', 
                                   help="Those categories are used to group similar products for point of sale.")

    _defaults = {
        'type' : 'product',
    }

    @api.multi
    @api.onchange('categ_id')
    def _align_categories(self):
        if self.categ_id.name:
            poscateg =self.env['pos.category'].search([('name', '=', self.categ_id.name)])[0]
            self.pos_categ_id = poscateg.id

    @api.one
    def _get_total_with_margin(self):
        _logger.info('Compute margin')
        _logger.info('Compute margin %s %d',self.categ_id.name,self.categ_id.profit_margin)
        if self.categ_id.name and self.categ_id.profit_margin > 0:
            margin_amount = self.standard_price * self.categ_id.profit_margin/100
        else:
            margin_amount = self.standard_price * 0.05
        self.total_with_margin = self.standard_price + margin_amount

    def _get_main_supplier_info(self):
        return self.seller_ids.sorted(key=lambda seller: seller.date_start, reverse=True)

    @api.one
    @api.depends('seller_ids')
    def _compute_cost(self):
        currency = self.currency_id
        total_taxes=0
        suppliers = self._get_main_supplier_info()
        if(len(suppliers) > 0):
            discounted_sell_unit_price = suppliers[0].price * (self.uom_po_id.factor/self.uom_id.factor) * (1-suppliers[0].discount/100)
            self.total_with_margin = discounted_sell_unit_price 
            for taxes_id in self.supplier_taxes_id:
                total_taxes += currency.round(taxes_id._compute_amount(discounted_sell_unit_price, discounted_sell_unit_price)) 
            self.total_with_margin += total_taxes            
            if self.categ_id.name and self.categ_id.profit_margin > 0:
                self.total_with_margin = self.total_with_margin * (1+self.categ_id.profit_margin/100)
            else:
                self.total_with_margin = self.total_with_margin * (1+0.05)

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
    

class stock_change_product_qty(models.TransientModel):
    _inherit = "stock.change.product.qty"
    
    def default_get(self, cr, uid, fields, context):
        res = super(stock_change_product_qty, self).default_get(cr, uid, fields, context=context)
        #location_ids = self.env['stock.location'].search(['&',('active','=',True),('usage', '=', 'internal')])
        location_ids=self.pool.get('stock.location').search(cr, uid, ['&',('active','=',True),('usage', '=', 'internal')], context=context)
            
        res['location_id'] = location_ids[0]
        return res