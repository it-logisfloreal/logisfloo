# -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from openerp import exceptions
from datetime import datetime

import logging
_logger = logging.getLogger(__name__)


class LogisflooPurchaseOrder(models.Model):
    _inherit = 'purchase.order'
        
    tpty_partner_id = fields.Many2one('res.partner', string='ThirdParty Partner', change_default=True,
        required=False, track_visibility='always') 
    isShopReceipt = fields.Boolean(String='Is Shop Receipt', default=False)
    RoundingAmount = fields.Monetary(string='Rounding amount')
    RebateAmount = fields.Monetary(string='Rebate amount')

    state = fields.Selection([
        ('draft', 'Draft PO'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('deposite', 'Deposite'),
        ('receipt', 'Draft Receipt'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
        ], string='Status', readonly=True, index=True, copy=False, default='draft', track_visibility='onchange')

    @api.onchange('isShopReceipt') 
    def _set_tpty_partner(self):
        _logger.info('Default tpty')
        if self.isShopReceipt:
            _logger.info('isShopReceipt computing')
            self.tpty_partner_id = self.env['res.users'].browse(self.env.uid).partner_id
                
    @api.multi
    def button_undo(self):
        if self.isShopReceipt:
            # Should not be used since all the accounting and inventory lines are commited when the record reaches the done state.
            # Undo button is hidden on the form for receipt in done state.
            self.write({'state': 'receipt'})
        else:
            self.write({'state': 'purchase'})

    @api.multi
    def button_deposite(self):
        self.write({'state': 'deposite'})

    @api.onchange('RoundingAmount', 'RebateAmount') 
    def _update_adjusted_amounts(self):
        self._amount_all()
        self.amount_total = self.amount_untaxed + self.amount_tax + self.RebateAmount + self.RoundingAmount
        
    @api.multi
    def button_receipt_completed(self):
        # set default state to draft to make stock.picking happy
        self = self.with_context(default_state='draft')
        # set po state to draft to make button_confirm do some work
        self.write({'state': 'draft'})
        self.button_confirm()
        for pick in self.picking_ids:
            wiz_act = pick.do_new_transfer()
            wiz = self.env[wiz_act['res_model']].browse(wiz_act['res_id'])
            wiz.process()
        # create and finalise invoice 
        invoice = self.env['account.invoice'].with_context(
            type='in_invoice').create({
                'partner_id': self.partner_id.id,
                'origin': self.name,
                'purchase_id': self.id,
                'reference': self.partner_ref,
                'tpty_partner_id': self.tpty_partner_id.id,
                'date_invoice': self.date_order,
                'date_due': self.date_order,
                'account_id': self.partner_id.property_account_payable_id.id,
            })            
        invoice.purchase_order_change()
        property_adjustinvoice_account = self.env['ir.property'].search([('name', '=', 'property_account_rebate')], limit=1)
        if self.RoundingAmount != 0:
            invoice_line = self.env['account.invoice.line']
            invoice_line.create({
                'name' : 'Rounding amount',
                'price_unit' : self.RoundingAmount,
                'quantity' : 1.0,
                'invoice_id' : invoice.id,
                'account_id' : property_adjustinvoice_account.value_reference.split(',')[1],
                })
        if self.RebateAmount != 0:
            invoice_line = self.env['account.invoice.line']
            invoice_line.create({
                'name' : 'Rebate amount',
                'price_unit' : self.RebateAmount,
                'quantity' : 1.0,
                'invoice_id' : invoice.id,
                'account_id' : property_adjustinvoice_account.value_reference.split(',')[1],
                })
        invoice.signal_workflow('invoice_open')
        self.write({'state': 'done'})

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

    tpty_partner_id = fields.Many2one('res.partner', string='ThirdParty Partner', change_default=True,
        required=False, readonly=True, states={'draft': [('readonly', False)], 'open': [('readonly', False)]},
        track_visibility='always')    

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
        _logger.info('Invoice id %s',self.env.context.get('InvoiceID'))
        
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
    # This is the master with access to the company property
    # use this one as a base to show the right form
    # or do the opposite ... call this one as an implementer when the data is known
        
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
        _logger.info('Account id %s',self.property_adjustinvoice_account.id)
        _logger.info('InvoiceID: %s', InvoiceID)
        #WizWindowTitle = "Compute the amount from the vendor's invoice."
        # Set the wizard window name directly in french
        # Translation of the action window name does not works when called from the code
        WizWindowTitle = "Calculer le montant à partir de la facture du fournisseur."
        return {
                'name': WizWindowTitle,
                'res_model': 'logisfloo.calcadjust.wizard',
                'src_model': 'account.invoice',
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
    
class LogisflooPayment(models.Model):
    _inherit = 'account.payment'

    property_journal_paid_by3rd_pty_id = fields.Many2one(
        'account.journal', 
        company_dependent=True,
        string="Paid by 3rd party Journal", 
        domain="[('deprecated', '=', False)]",
        help="This journal will be used to record the payment by third party",
        required=True)
            
    @api.multi
    def post(self):
        _logger.info('Going through LogisflooPayment *************')
        # if there is a third party payment, then we only process one invoice at a time (I've no time to do more)    
        # if there is no third party payment, then we let it through the standard code       
        
        if len(self) > 1:
            raise UserError(_("Only one payment can be processed at a time. Trying to post %s payments") % len(self))

        if len(self.invoice_ids) > 1:
            for inv in self.invoice_ids:
                if inv.tpty_partner_id:  
                    raise UserError(_("Only one invoice with third party payer can be processed at a time."))
              
        if self.invoice_ids[0].partner_id != self.invoice_ids[0].tpty_partner_id and self.invoice_ids[0].tpty_partner_id:
            # Create the vendor entries in the paid by 3rd party journal
            old_journal_id=self.journal_id
            self.journal_id=self.property_journal_paid_by3rd_pty_id
            super(LogisflooPayment,self).post()
            self.journal_id=old_journal_id
            
            # Create the 3rd party entries in the request journal
            vendor_id = self.invoice_ids[0].partner_id 
            old_name=self.name
            
            self.partner_id = self.invoice_ids[0].tpty_partner_id
            self.name = self.env['ir.sequence'].with_context(ir_sequence_date=self.payment_date).next_by_code('account.tptypayment.supplier.invoice')
            amount = self.amount * (self.payment_type in ('outbound', 'transfer') and 1 or -1)
            self._create_tpty_payment_entry(amount)
            
            self.partner_id = vendor_id
            self.name=old_name
        else:
            super(LogisflooPayment,self).post()
            
    def _create_tpty_payment_entry(self, amount):
        """ Create a journal entry corresponding to a payment, if the payment references invoice(s) they are reconciled.
            Return the journal entry.
        """
        aml_obj = self.env['account.move.line'].with_context(check_move_validity=False)
        invoice_currency = False
        if self.invoice_ids and all([x.currency_id == self.invoice_ids[0].currency_id for x in self.invoice_ids]):
            #if all the invoices selected share the same currency, record the paiement in that currency too
            invoice_currency = self.invoice_ids[0].currency_id
        debit, credit, amount_currency, currency_id = aml_obj.with_context(date=self.payment_date).compute_amount_fields(amount, self.currency_id, self.company_id.currency_id, invoice_currency)

        move = self.env['account.move'].create(self._get_move_vals())

        #Write line corresponding to invoice payment  
        counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
        counterpart_aml_dict.update(self._get_tpty_counterpart_move_line_vals(self.invoice_ids))
        counterpart_aml_dict.update({'currency_id': currency_id})
        aml_obj.create(counterpart_aml_dict)

        #Write counterpart lines
        if not self.currency_id != self.company_id.currency_id:
            amount_currency = 0
        liquidity_aml_dict = self._get_shared_move_line_vals(credit, debit, -amount_currency, move.id, False)
        liquidity_aml_dict.update(self._get_liquidity_move_line_vals(-amount))
        aml_obj.create(liquidity_aml_dict)

        move.post()
        return move

    def _get_tpty_counterpart_move_line_vals(self, invoice=False):
        if self.payment_type == 'transfer':
            name = self.name
        else:
            name = ''
            if self.partner_type == 'customer':
                if self.payment_type == 'inbound':
                    name += _("Customer Payment")
                elif self.payment_type == 'outbound':
                    name += _("Customer Refund")
            elif self.partner_type == 'supplier':
                if self.payment_type == 'inbound':
                    name += _("Vendor Refund")
                elif self.payment_type == 'outbound':
                    name += _("Third Party Payment")
            if invoice:
                name += ': '
                for inv in invoice:
                    if inv.move_id:
                        name += inv.number + ', '
                name = name[:len(name)-2] 
        return {
            'name': name,
            'account_id': self.property_journal_paid_by3rd_pty_id.default_debit_account_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id != self.company_id.currency_id and self.currency_id.id or False,
            'payment_id': self.id,
        }
        
class LogisflooCalcAdjustPOWizard(models.TransientModel):
    _name = 'logisfloo.calcadjustpo.wizard'
        
    @api.multi
    def dont_close_form(self):
        self.ensure_one()
        return {"type": "set_scrollTop",}
    
    @api.multi
    def calculate(self):
        _logger.info('Add calculated line for %s',self.env.context.get('Description', False))
        purchase_order = self.env['purchase.order'].browse(self.env.context.get('active_id'))
        purchase_order.RoundingAmount = 0
        purchase_order.RebateAmount = 0
        purchase_order._update_adjusted_amounts()
        AdjustmentAmount = self.InvoicedTotalAmount - purchase_order.amount_total
        if self.env.context.get('Description', False) == "Arrondi":
            purchase_order.RoundingAmount = AdjustmentAmount
        else:
            purchase_order.RebateAmount = AdjustmentAmount
        purchase_order._update_adjusted_amounts()
                
    company_currency_id = fields.Many2one('res.currency', string='Currency')
    InvoicedTotalAmount = fields.Monetary(string='Amount on invoice', currency_field='company_currency_id')
    
class LogisflooAdjustPOWizard(models.TransientModel):
    _name = 'logisfloo.adjustpo.wizard'

    @api.multi
    def dont_close_form(self):
        self.ensure_one()
        return {"type": "set_scrollTop",}
            
    @api.multi
    def _compute_default(self):
        _logger.info('Start _compute_default')
        purchase_order = self.env['purchase.order'].browse(self.env.context.get('active_id'))
        return purchase_order.amount_total
    
    @api.multi
    def add_adjustment_line(self):
        _logger.info('Add adjust line for %s',self.env.context.get('Description', False))
        purchase_order=self.env['purchase.order'].browse(self.env.context.get('active_id'))
        if self.env.context.get('Description', False) == "Arrondi":
            purchase_order.RoundingAmount = self.AdjustmentAmount
        else:
            purchase_order.RebateAmount = self.AdjustmentAmount
        purchase_order._update_adjusted_amounts()
    
    @api.multi
    def open_calculator(self):
        _logger.info('Start calculator')
        mydesc = self.env.context.get('Description', False)
        PurchaseOrderID = self.env.context.get('active_id')
        _logger.info('Description: %s', mydesc)
        _logger.info('PurchaseOrderID: %s', PurchaseOrderID)
        #WizWindowTitle = "Compute the amount from the vendor's invoice."
        # Set the wizard window name directly in french
        # Translation of the action window name does not works when called from the code
        WizWindowTitle = "Calculer le montant à partir du ticket de caisse."
        return {
                'name': WizWindowTitle,
                'res_model': 'logisfloo.calcadjustpo.wizard',
                'src_model': 'purchase.order',
                'view_mode': 'form', 
                'type': 'ir.actions.act_window',
                'target': 'new',
                'context': {'PurchaseOrderID': PurchaseOrderID, 
                            'Description': mydesc,
                            'ComputedTotalAmount': self.ComputedTotalAmount,
                            }
            }
                
    company_currency_id = fields.Many2one('res.currency', string='Currency')
    ComputedTotalAmount = fields.Monetary(string='Amount in Odoo', 
                                          currency_field='company_currency_id', 
                                          default=_compute_default, 
                                          readonly=True)
    InvoicedTotalAmount = fields.Monetary(string='Amount on invoice', currency_field='company_currency_id')
    AdjustmentAmount = fields.Monetary(string='Adjustment amount', currency_field='company_currency_id')