 # -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.exceptions import UserError
import openerp.addons.decimal_precision as dp

import logging
_logger = logging.getLogger(__name__)

class LogisflooProduct(models.Model):
    _inherit = 'product.template'
    
    total_with_margin = fields.Float(compute='_compute_recommended_price', store=False, string="Total Sales Price with Margin")
    total_cost = fields.Float(compute='_get_cost', store=False, string="Coût total sans transport")
    actual_margin = fields.Float(compute='_compute_actual_margin', store=True, string="Actual Margin")
    number_of_suppliers = fields.Integer(compute='_compute_suppliers', store=True, string="Number of suppliers")
    # if only one provider show price computed price (incl tax and rebate)
    reference_price = fields.Float(string='Invoice Price')
    producer = fields.Char(string="Producer")
    default_code = fields.Char(store=True)
    internal_ref = fields.Char(string="Internal Reference")
    pos_categ_id = fields.Many2one('pos.category','Point of Sale Category', 
                                   help="Those categories are used to group similar products for point of sale.")

    _defaults = {
        'type' : 'product',
    }

    @api.one
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
    @api.depends('seller_ids.name')
    def _compute_suppliers(self):
        self.number_of_suppliers = len(self._get_main_supplier_info())

    @api.one
    @api.depends('list_price','standard_price')
    def _compute_actual_margin(self):
        if self.total_cost != 0:
            self.actual_margin = (self.list_price/self.total_cost) * 100 - 100
        else:
            self.actual_margin = 0

    def _search_actual_margin(self, operator, value):
        if operator == 'like':
            operator = 'illkie'
        return [('name', operator, value)]

    @api.one
    def _get_cost(self):
        self.ensure_one()
        result = 0.0
        currency = self.currency_id
        total_taxes = 0
        suppliers = self._get_main_supplier_info()
        if(len(suppliers) > 0):
            discounted_sell_unit_price = currency.round(suppliers[0].price * (self.uom_po_id.factor/self.uom_id.factor) * (1-suppliers[0].discount/100))
            result = discounted_sell_unit_price 
            for taxes_id in self.supplier_taxes_id:
                total_taxes += currency.round(taxes_id._compute_amount(discounted_sell_unit_price, discounted_sell_unit_price)) 
            result += total_taxes
        self.total_cost = result                

    @api.one
    @api.depends('seller_ids')
    def _compute_recommended_price(self):
        self.total_with_margin = self.total_cost            
        if self.categ_id.name and self.categ_id.profit_margin > 0:
            self.total_with_margin = self.total_with_margin * (1+self.categ_id.profit_margin/100)
        else:
            self.total_with_margin = self.total_with_margin * (1+0.05)

    @api.model
    def rebuild_full_price_history(self):    
        # Call this from an automated action
        _logger.info('Rebuild full price history')
        self.env['product.template'].with_context(active_test=False).search([]).rebuild_product_price_history()

    @api.multi
    def rebuild_product_price_history(self):

        def _compute_price(line):
            currency = line.invoice_id and line.invoice_id.currency_id or None
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = 0.0
            if line.invoice_line_tax_ids:
                taxes = line.invoice_line_tax_ids.compute_all(price, currency, 1.0)['total_included']
            return taxes

        for template in self:
            product_product_recs=self.env['product.product'].with_context(active_test=False).search([('product_tmpl_id','=',template.id)])
            price_history=self.env['product.price.history']
            currency = template.currency_id
            tax_ratio = 1
            suppliers = template._get_main_supplier_info()
            for taxes_id in template.supplier_taxes_id:
                tax_ratio += currency.round(taxes_id._compute_amount(1.0, 1.0)) 
            tax_unit_ratio = (template.uom_po_id.factor/template.uom_id.factor)*tax_ratio
            _logger.info('Rebuild [%s] price history for %d product instances (tax ratio %f)', template.name, len(product_product_recs), tax_ratio)
            for product in product_product_recs:
                price_history.search([('product_id', '=', product.id)]).unlink()
                invoice_lines = self.env['account.invoice.line'].search([('product_id', '=', product.id), ('purchase_line_id', '!=', False)], 
                                    order='create_date asc')
                data_items=[(x.create_date,_compute_price(x) * (template.uom_po_id.factor/template.uom_id.factor)) for x in invoice_lines if x.quantity > 0]
                # create a price history for the product creation date, so we have a cost for the full product life
                if len(data_items) == 0:
                    # There was no invoice line, use the supplier price or the list price to guess a cost
                    if len(suppliers) > 0:
                        data_items.append((product.create_date, template._get_cost()))
                    else:
                        data_items.append((product.create_date, template.list_price*0.95))
                else:
                    # use the first invoice price
                    first_price = data_items[0][1]
                    data_items.insert(0, (product.create_date, first_price))
                for item in data_items:
                    price_history.create({
                        'company_id': self.env.user.company_id.id,
                        'product_id': product.id,
                        'datetime': item[0],
                        'cost': item[1],
                        })
                # update standard_price to match the latest invoice line
                product.standard_price = data_items[len(data_items)-1][1]
                _logger.info('-> created %d records', len(data_items)+1)
            template._compute_actual_margin()

    @api.model
    def rebuild_full_customer_price_history(self):    
        # Call this from an automated action
        _logger.info('Rebuild full customer price history')
        self.env['product.template'].with_context(active_test=False).search([]).rebuild_product_customer_price_history()

    @api.multi
    def rebuild_product_customer_price_history(self):
        for template in self:
            product_product_recs = self.env['product.product'].with_context(active_test=False).search([('product_tmpl_id','=',template.id)])
            customer_price_history = self.env['product.customer.price.history']
            currency = template.currency_id
            suppliers = template._get_main_supplier_info()
            _logger.info('Rebuild [%s] customer price history for %d product instances.', template.name, len(product_product_recs))
            for product in product_product_recs:
                customer_price_history.search([('product_id', '=', product.id)]).unlink()
                pos_order_lines = self.env['pos.order.line'].search([('product_id', '=', product.id)], order='create_date asc')
                data_items = [(x.create_date, x.price_unit) for x in pos_order_lines if x.qty > 0]
                # create a customer price history for the product creation date, so we have a price for the full product life
                if len(data_items) == 0:
                    # There was no invoice line, use the supplier price or the list price to guess a cost
                    if len(suppliers) > 0:
                        data_items.append((product.create_date, template._get_cost()))
                    else:
                        data_items.append((product.create_date, template.list_price*0.95))
                else:
                    # use the first invoice price
                    first_price = data_items[0][1]
                    data_items.insert(0, (product.create_date, first_price))
                # Filter records so we only keep changing prices
                data_items = [v for i, v in enumerate(data_items) if i == 0 or v[1] != data_items[i-1][1]]
                for item in data_items:
                    customer_price_history.create({
                        'company_id': self.env.user.company_id.id,
                        'product_id': product.id,
                        'datetime': item[0],
                        'price': item[1],
                        })
                _logger.info('-> created %d records', len(data_items)+1)

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
    
class produce_customer_price_history(models.Model):
    """
    Keep track of the ``product.template`` customer prices as they are changed.
    """

    _name = 'product.customer.price.history'
    _rec_name = 'datetime'
    _order = 'datetime asc'

    def _get_default_company(self, cr, uid, context=None):
        if 'force_company' in context:
            return context['force_company']
        else:
            company = self.pool['res.users'].browse(cr, uid, uid,
                context=context).company_id
            return company.id if company else False

    company_id = fields.Many2one('res.company', required=True, default=_get_default_company)
    product_id = fields.Many2one('product.product', 'Product', required=True, ondelete='cascade')
    datetime = fields.Datetime(string='Date', default=fields.datetime.now)
    price = fields.Float('Price', digits=dp.get_precision('Product Price'))

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
