from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from openerp import exceptions

import logging
_logger = logging.getLogger(__name__)


class LogisflooPurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    #state = fields.Selection(selection_add=[('deposite', 'Deposite')])


    state = fields.Selection([
        ('draft', 'Draft PO'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('deposite', 'Deposite'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
        ], string='Status', readonly=True, index=True, copy=False, default='draft', track_visibility='onchange')

    @api.multi
    def button_undo(self):
        self.write({'state': 'purchase'})

    @api.multi
    def button_deposite(self):
        self.write({'state': 'deposite'})

class LogisflooPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    
    discount = fields.Float(string='Discount')

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            taxes = line.taxes_id.compute_all(line.price_unit * (1-(line.discount or 0.0) / 100.0), line.order_id.currency_id, line.product_qty, product=line.product_id, partner=line.order_id.partner_id)
            line.update({
                'price_tax': taxes['total_included'] - taxes['total_excluded'],
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    def _get_seller_discount(self):
        if not self.product_id:
            return 
        seller = self.product_id._select_seller(
            self.product_id,
            partner_id=self.partner_id,
            quantity=self.product_qty,
            date=self.order_id.date_order and self.order_id.date_order[:10],
            uom_id=self.product_uom)
        if not seller:
            return 
        return seller.discount
    
    # Override the PO line onchange quantity method to update the seller discount on the PO line
    def _onchange_quantity(self):
        super(LogisflooPurchaseOrderLine,self)._onchange_quantity()
        self.discount = self._get_seller_discount()

    # Override the PO line create method to add the seller discount on the PO line
    @api.model
    def create(self, values):
        record = super(LogisflooPurchaseOrderLine,self).create(values)
        record['discount'] = record._get_seller_discount()
        return record
    
class LogisflooAccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _prepare_invoice_line_from_po_line(self, line):
        data=super(LogisflooAccountInvoice,self)._prepare_invoice_line_from_po_line(line)
        data['discount'] = line.discount or 0.0
        return data
 
class LogisflooCalcAdjustWizard(models.TransientModel):
    _name = 'logisfloo.calcadjust.wizard'
        
    @api.multi
    def dont_close_form(self):
        self.ensure_one()
        return {"type": "set_scrollTop",}
    
    @api.multi
    @api.onchange('InvoicedTotalAmount')
    def compute_rebate_amount(self):
        self.CalcRebateAmount = self.InvoicedTotalAmount - self.ComputedTotalAmount
        
    @api.multi
    def _compute_default(self):
        _logger.info('Start _compute_default')
        Amount = self.env.context.get('ComputedTotalAmount')
        return Amount
        
    @api.multi
    def calculate(self):
        _logger.info('Add calculated line for %s',self.env.context.get('Description', False))
        _logger.info('Account id %s',self.env.context.get('AccountID'))
        invoice_line = self.env['account.invoice.line']
        invoice_line.create({
            'name' : self.env.context.get('Description', False),
            'price_unit' : self.CalcRebateAmount,
            'quantity' : 1.0,
            'invoice_id' : self.env.context.get('InvoiceID'),
            'account_id' : self.env.context.get('AccountID'),
            })
                
    company_currency_id = fields.Many2one('res.currency', string='Currency')
    ComputedTotalAmount = fields.Monetary(string='Amount in Odoo', 
                                          currency_field='company_currency_id', 
                                          default=_compute_default, 
                                          readonly=True)
    InvoicedTotalAmount = fields.Monetary(string='Amount on invoice', currency_field='company_currency_id')
    CalcRebateAmount = fields.Monetary(string='Rebate amount', currency_field='company_currency_id', compute='compute_rebate_amount')
    
class LogisflooAdjustInvoiceWizard(models.TransientModel):
    _name = 'logisfloo.adjustinvoice.wizard'
        
    @api.multi
    def dont_close_form(self):
        self.ensure_one()
        return {"type": "set_scrollTop",}
            
    @api.multi
    def _compute_default(self):
        _logger.info('Start _compute_default')
        Invoice = self.env['account.invoice'].browse(self.env.context.get('active_id'))
        return Invoice.amount_total

    @api.multi
    def _get_invoice_id(self):
        return self.env.context.get('active_id')
    
    @api.multi
    def add_adjustment_line(self):
        _logger.info('Add adjust line for %s',self.env.context.get('Description', False))
        _logger.info('Account id %s',self.property_adjustinvoice_account.id)
        invoice_line = self.env['account.invoice.line']
        invoice_line.create({
            'name' : self.env.context.get('Description', False),
            'price_unit' : self.AdjustmentAmount,
            'quantity' : 1.0,
            'invoice_id' : self.env.context.get('active_id'),
            'account_id' : self.property_adjustinvoice_account.id,
            })
    
    @api.multi
    def open_calculator(self):
        _logger.info('Start calculator')
        mydesc = self.env.context.get('Description', False)
        InvoiceID = self.env.context.get('active_id')
        _logger.info('Description: %s', mydesc)
        _logger.info('InvoiceID: %s', InvoiceID)
        return {
                'name': 'Calculate',
                'res_model': 'logisfloo.calcadjust.wizard',
                'src_model': 'account.invoice',
                #'view_id': "logisfloo_cacladjust_wizard_form",
                'view_mode': 'form', 
                'type': 'ir.actions.act_window',
                'target': 'new',
                'context': {'InvoiceID': InvoiceID, 
                            'Description': mydesc,
                            'ComputedTotalAmount': self.ComputedTotalAmount,
                            'AccountID': self.property_adjustinvoice_account.id,
                            }
            }
                
    company_currency_id = fields.Many2one('res.currency', string='Currency')
    property_adjustinvoice_account = fields.Many2one(
        'account.account', 
        company_dependent=True,
        string="Adjustment Account", 
        domain="[('deprecated', '=', False)]",
        help="This account will be used to record the invoice adjustment",
        required=True)
    ComputedTotalAmount = fields.Monetary(string='Amount in Odoo', 
                                          currency_field='company_currency_id', 
                                          default=_compute_default, 
                                          readonly=True)
    InvoicedTotalAmount = fields.Monetary(string='Amount on invoice', currency_field='company_currency_id')
    AdjustmentAmount = fields.Monetary(string='Adjustment amount', currency_field='company_currency_id')
        
        