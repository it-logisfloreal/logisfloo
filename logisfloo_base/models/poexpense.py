# -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from openerp import exceptions
from datetime import datetime
from datetime import timedelta

import logging
_logger = logging.getLogger(__name__)

class LogisflooPOExpense(models.Model):
    _name = "logisfloo.poexpense"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'name desc'
    
    name = fields.Char('PO Expense Reference', required=True, index=True, copy=False, default='New')    
    payee_partner_id = fields.Many2one('res.partner', string='Payee', required=True, track_visibility='onchange')
    transport_type_id = fields.Many2one('logisfloo.potransportcost', string='Transport Type', required=True, track_visibility='onchange')
    distance = fields.Float(string='Distance',required=True, track_visibility='onchange', default=0.0)
    purchase_id = fields.Many2one('purchase.order', required=False, string='Add Purchase Order', track_visibility='onchange', help='')
    state = fields.Selection([
            ('draft','Draft'),
            ('open', 'Open'),
            ('paid', 'Paid'),
            ('cancel', 'Cancelled'),
        ], string='Status', index=True, readonly=True, default='draft', track_visibility='onchange', help="")
    currency_id = fields.Many2one('res.currency', string='Currency') 
    expense_amount = fields.Monetary(string='Amount', currency_field='currency_id', compute='_compute_amount', readonly=True)
    trip_date = fields.Date(string='Trip Date', readonly=True, states={'draft': [('readonly', False)]}, default=datetime.now().date(),
                            index=True, track_visibility='onchange', help="Keep empty to use the current date")
    date_due = fields.Date(string='Due Date', readonly=True, states={'draft': [('readonly', False)]}, 
                           default=datetime.now().date() + timedelta(days = 7) ,
                           index=True, track_visibility='onchange', help="Keep empty to use the current date")

# not sure we need this, can be calculated at the time we pay the expense
#    property_expense_journal_id = fields.Many2one(
#        'account.journal', 
#        company_dependent=True,
#        string="Expense Journal", 
#        domain="[('deprecated', '=', False)]",
#        help="This journal will be used to record the expense payment.",
#        required=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('logisfloo.poexpense') or '/'
        return super(LogisflooPOExpense, self).create(vals)

    @api.one
    @api.depends('distance', 'transport_type_id')
    def _compute_amount(self):
        if self.distance and self.transport_type_id:
            amount = self.distance * self.transport_type_id.unit_cost
        else:
            amount = 0.0
        self.expense_amount=amount

    @api.multi
    def button_confirm(self):
        self.write({'state': 'open'})
        return {}
    
    @api.multi
    def button_pay(self):
        self.write({'state': 'paid'})
        return {}

    @api.multi
    def button_cancel(self):
        self.write({'state': 'cancel'})
        return {}
    
    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})
        return {}
        
class LogisflooPOTransportCost(models.Model):
    _name = "logisfloo.potransportcost"
        
    currency_id = fields.Many2one('res.currency', string='Currency') 
    unit_cost = fields.Monetary(string='Cost per km', currency_field='currency_id')
    name=fields.Char('Name',required=True)
