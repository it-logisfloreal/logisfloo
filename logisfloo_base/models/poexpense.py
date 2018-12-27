# -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from openerp import exceptions
from datetime import datetime
from datetime import timedelta
import json

import logging
_logger = logging.getLogger(__name__)

class LogisflooPOExpense(models.Model):
    _name = "logisfloo.poexpense"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'name desc'

    @api.model
    def _default_currency(self):
        return self.company_id.currency_id or self.env.user.company_id.currency_id
    
    name = fields.Char('PO Expense Name', required=True, index=True, copy=False, default='New')
    ref = fields.Char('PO Expense Reference', required=True, index=True, copy=False, compute='_compute_ref')    
    payee_partner_id = fields.Many2one('res.partner', string='Payee', required=True, track_visibility='onchange')
    transport_type_id = fields.Many2one('logisfloo.potransportcost', string='Transport Type', required=True, track_visibility='onchange')
    transport_unit = fields.Char('Transport Unit',related='transport_type_id.unit')
    quantity = fields.Float(string='Quantity',required=True, track_visibility='onchange', default=0.0)
    purchase_id = fields.Many2one('purchase.order', required=False, string='Purchase Order', track_visibility='onchange', help='')
    state = fields.Selection([
            ('draft','Draft'),
            ('open', 'Open'),
            ('paid', 'Paid'),
            ('reject', 'Rejected'),
        ], string='Status', index=True, readonly=True, default='draft', track_visibility='onchange', help="")
    currency_id = fields.Many2one('res.currency', string='Currency',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=_default_currency, track_visibility='always') 
    expense_amount = fields.Monetary(string='Amount', currency_field='currency_id', compute='_compute_amount', readonly=True, store=True)
    purchased_amount = fields.Monetary(string='Purchased Amount', currency_field='currency_id', compute='_compute_purchased_amount', readonly=True)
    cost_ratio = fields.Float(string='Cost ratio', compute='_compute_cost_ratio', readonly=True, digits=(3,0))
    trip_date = fields.Date(string='Trip Date', readonly=True, states={'draft': [('readonly', False)]}, default=datetime.now().date(),
                            index=True, track_visibility='onchange', help="Keep empty to use the current date")
    date_due = fields.Date(string='Due Date', readonly=True, states={'draft': [('readonly', False)]}, 
                           default=datetime.now().date() + timedelta(days = 7) ,
                           index=True, track_visibility='onchange', help="Keep empty to use the current date")
    move_name = fields.Char(string='Journal Entry', readonly=False,
        default=False, copy=False,
        help="Technical field holding the number given to the expense, automatically set when the expense is validated then stored to set the same number again if the invoice is cancelled, set to draft and re-validated.")
# to be added on form: move_id, move_name
    move_id = fields.Many2one('account.move', string='Journal Entry',
        readonly=True, index=True, ondelete='restrict', copy=False,
        help="Link to the automatically generated Journal Items.")
    property_expense_journal_id = fields.Many2one(
        'account.journal', 
        company_dependent=True,
        string="Expense Journal", 
        domain="[('deprecated', '=', False)]",
        help="This journal will be used to record the expense payment.",
        required=True)
    property_ref_ratio = fields.Float(
        company_dependent=True,
        string="Max ratio to pay expense", 
        help="This is maximum expense/purchase amount allowed to pay an expense to preserve the sell margin.",
        required=True)
    company_id = fields.Many2one('res.company', string='Company', change_default=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get('logisfloo.poexpense'))
    payments_widget = fields.Text(compute='_get_payment_info_JSON')


    def _needaction_domain_get(self, cr, uid, context=None):
        return [('state', '=', 'open')] 
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('logisfloo.poexpense') or '/'
        return super(LogisflooPOExpense, self).create(vals)

    @api.multi
    def unlink(self):
        if self.state in ['paid','reject']:
            raise UserError(_('A paid or rejected expense cannot be deleted.'))
        else:
            super(LogisflooPOExpense, self).unlink()
    
    @api.one
    @api.depends('quantity', 'transport_type_id')
    def _compute_amount(self):
        if self.quantity and self.transport_type_id:
            amount = self.quantity * self.transport_type_id.unit_cost
        else:
            amount = 0.0
        self.expense_amount=amount

    @api.depends('purchase_id')
    def _compute_purchased_amount(self):
        if self.purchase_id:
            self.purchased_amount = self.purchase_id.amount_total
        else:
            self.purchased_amount = 0.0

    @api.depends('purchased_amount', 'expense_amount')
    def _compute_cost_ratio(self):
        if self.purchased_amount != 0:
            self.cost_ratio=self.expense_amount/self.purchased_amount*100
        else:
            self.cost_ratio=0.0

    @api.depends('purchase_id')
    def _compute_ref(self):
        if self.purchase_id.name:
            ref="Transport: " + self.purchase_id.name
        else:
            ref="No expense linked"
        self.ref=ref
        
    @api.multi
    def button_confirm(self):
        self.write({'state': 'open'})
        return {}

    @api.multi
    def button_reject(self):
        self.write({'state': 'reject'})
        return {}
        
    @api.multi
    def button_pay(self):
        if self.cost_ratio < self.property_ref_ratio:
            self.do_pay()
        else:
            raise UserError(_('This expense amount is more than %2.2f %% of the purchase amount and cannot be paid.' 
            ' Ask an administrator to process the payment or reject this expense.') % self.property_ref_ratio)
        return {}
    
    @api.multi
    def button_force_pay(self):
        self.do_pay()
        return {}

    @api.multi
    def do_pay(self):
        self.action_move_create()
        return {}        
    
    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})
        return {}

    @api.multi
    def _move_line_get(self):
        account_move = []
        for expense in self:
            account = expense.property_expense_journal_id.default_debit_account_id
            move_line = {
                    'type': 'src',
                    'name': expense.name.split('\n')[0][:64],
                    'price_unit': False,
                    'quantity': False,
                    'price': expense.expense_amount,
                    'account_id': account.id,
                    'product_id': False,
                    'uom_id': False,
                    'analytic_account_id': False,
                }
            account_move.append(move_line)
        return account_move

    @api.multi
    def _compute_expense_totals(self, company_currency, account_move_lines, move_date):
        '''
        internal method used for computation of total amount of an expense in the company currency and
        in the expense currency, given the account_move_lines that will be created. It also do some small
        transformations at these account_move_lines (for multi-currency purposes)

        :param account_move_lines: list of dict
        :rtype: tuple of 3 elements (a, b ,c)
            a: total in company currency
            b: total in hr.expense currency
            c: account_move_lines potentially modified
        '''
        self.ensure_one()
        total = 0.0
        total_currency = 0.0
        for line in account_move_lines:
            line['currency_id'] = False
            line['amount_currency'] = False
            if self.currency_id != company_currency:
                line['currency_id'] = self.currency_id.id
                line['amount_currency'] = line['price']
                line['price'] = self.currency_id.with_context(date=move_date or fields.Date.context_today(self)).compute(line['price'], company_currency)
            total -= line['price']
            total_currency -= line['amount_currency'] or line['price']
        return total, total_currency, account_move_lines

    def _prepare_move_line(self, line):
        '''
        This function prepares move line of account.move related to an expense
        '''
        partner_id = self.payee_partner_id.id
        return {
            'date_maturity': line.get('date_maturity'),
            'partner_id': partner_id,
            'name': line['name'][:64],
            'debit': line['price'] > 0 and line['price'],
            'credit': line['price'] < 0 and -line['price'],
            'account_id': line['account_id'],
            'analytic_line_ids': line.get('analytic_line_ids'),
            'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or -abs(line.get('amount_currency')),
            'currency_id': line.get('currency_id'),
            'tax_line_id': line.get('tax_line_id'),
            'tax_ids': line.get('tax_ids'),
            'ref': line.get('ref'),
            'quantity': line.get('quantity',1.00),
            'product_id': line.get('product_id'),
            'product_uom_id': line.get('uom_id'),
            'analytic_account_id': line.get('analytic_account_id'),
        }

    @api.multi
    def action_move_create(self):
        '''
        main function that is called when trying to create the accounting entries related to an expense
        '''
        if any(expense.state != 'open' for expense in self):
            raise UserError(_("You can only generate accounting entry for approved expense(s)."))

        if any(not expense.property_expense_journal_id for expense in self):
            raise UserError(_("Expenses must have an expense journal specified to generate accounting entries."))

        journal_dict = {}
        movedate = datetime.now().date()
        for expense in self:
            jrn = expense.property_expense_journal_id
            journal_dict.setdefault(jrn, [])
            journal_dict[jrn].append(expense)

        for journal, expense_list in journal_dict.items():
            #create the move that will contain the accounting entries
            move = self.env['account.move'].create({
                'journal_id': journal.id,
                'company_id': self.env.user.company_id.id,
                'date': movedate,
                'ref': self.ref,
            })
            for expense in expense_list:
                company_currency = expense.company_id.currency_id
                diff_currency_p = expense.currency_id != company_currency
                #one account.move.line per expense (+taxes..)
                move_lines = expense._move_line_get()

                #create one more move line, a counterline for the total on payable account
                total, total_currency, move_lines = expense._compute_expense_totals(company_currency, move_lines, movedate)
                emp_account = expense.property_expense_journal_id.default_credit_account_id

                move_lines.append({
                        'type': 'dest',
                        'name': expense.name.split('\n')[0][:64],
                        'price': total,
                        'account_id': emp_account.id,
                        'date_maturity': movedate,
                        'amount_currency': diff_currency_p and total_currency or False,
                        'currency_id': diff_currency_p and expense.currency_id.id or False,
                        'ref': expense.ref
                        })

                #convert eml into an osv-valid format
                _logger.info('prepare lines')
                lines = map(lambda x:(0, 0, expense._prepare_move_line(x)), move_lines)
                _logger.info('write move')
                move.with_context(dont_create_taxes=True).write({'line_ids': lines})
                expense.write({'move_id': move.id, 'state': 'paid'})
            move.post()
        return True

    @api.one
    @api.depends('move_id')
    def _get_payment_info_JSON(self):
        self.payments_widget = json.dumps(False)
        if self.move_id:
            info = {'title': _('Less Payment'), 'outstanding': False, 'content': []}
            move=self.move_id
            info['content'].append({
                'name': move.name,
                'journal_name': move.journal_id.name,
                'amount': move.amount,
                'currency': move.currency_id.symbol,
                'digits': [69, move.currency_id.decimal_places],
                'position': move.currency_id.position,
                'date': move.date,
                'payment_id': False,
                'move_id': move.id,
                'ref': move.ref,
            })
            self.payments_widget = json.dumps(info)
        
class LogisflooPOTransportCost(models.Model):
    _name = "logisfloo.potransportcost"
        
    currency_id = fields.Many2one('res.currency', string='Currency') 
    unit_cost = fields.Monetary(string='Cost per unit', currency_field='currency_id', track_visibility='onchange')
    unit = fields.Char('Unit', required=True, default='km', track_visibility='onchange')
    name=fields.Char('Name',required=True, track_visibility='onchange')
