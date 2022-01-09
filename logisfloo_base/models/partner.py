# -*- coding: utf-8 -*-
#import logging
#from openerp.osv import orm

from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from openerp.addons.logisfloo_base.tools import concat_names

import datetime
import logging
_logger = logging.getLogger(__name__)

class Partner(models.Model):
    _inherit = 'res.partner'

    first_name = fields.Char('First Name')
    last_name = fields.Char('Last Name', required=True)
    slate_number = fields.Integer('Slate Number')
    subscription_date = fields.Date('Subscription Date')
    subscription_event = fields.Char('Subscription Event', size=40)
    logisfloreal_tenant = fields.Boolean('Tenant Logis-Floréal')
    add_to_mailing_list = fields.Boolean('Add to Mailing List')
    welcome_email = fields.Boolean('Email de bienvenue envoyé', default=False)
    slate_balance = fields.Monetary(string='Slate Balance', compute='get_slate_balance', search='search_by_slate_balance')  
    slate_partners = fields.One2many("res.partner", "slate_number", domain=[],compute='get_slate_partners')   
    slate_last_fund_date = fields.Date("Last fund date", domain=[],compute='get_slate_last_fund_date', search='search_by_last_fund_date')
    slate_last_pay_date = fields.Date("Last payment date", domain=[],compute='get_slate_last_pay_date', search='search_by_last_pay_date')
    last_msg_date = fields.Date("Last message date", domain=[],compute='get_last_msg_date', search='search_by_last_msg_date')
    property_account_slate_id = fields.Many2one(
        'account.account', 
        company_dependent=True,
        string="Slate Account", 
        domain="[('deprecated', '=', False)]",
        help="This account will be used as the pre-paid slate account for the current partner",
        required=True)

    _defaults = {
    'slate_number':lambda self, cr, uid, context:self.pool.get('ir.sequence').get(cr, uid, 'slate.id'),
    }
    able_to_modify_slate_number = fields.Boolean(compute='set_access_for_slate_number', string='Is user able to modify the slate number?')

    def isduplicate(self, name, active):
        partners = self.env['res.partner'].search([('name', '=',name),('active', '=',active)])
        _logger.info('Checking for duplicate partner: %s and value %d', name, len(partners))
        if len(partners)>0:
            return True
        else:
            return False

    @api.multi
    def write(self, values):
        if self.name != values.get('name') and self.isduplicate(values.get('name'),True):
            raise ValidationError(_('%s already exists in the database.') % values.get('name'))
        if self.name != values.get('name') and self.isduplicate(values.get('name'),False):
            raise ValidationError(_('%s already exists in the database, but it is archived. Search the Archived records and unarchive it.') % values.get('name'))
        return super(Partner, self).write(values)

    @api.model
    def create(self, values):
        if self.isduplicate(values.get('name'),True):
            raise ValidationError(_('%s already exists in the database.') % values.get('name'))
        if self.isduplicate(values.get('name'),False):
            raise ValidationError(_('%s already exists in the database, but it is archived. Search the Archived records and unarchive it.') % values.get('name'))
        return super(Partner, self).create(values)

    def search_by_slate_balance(self, operator, value):
        _logger.info('Searching slate_balance with: %s and value %s', operator, value)
        if operator not in ('=', '!=', '<', '<=', '>', '>='):
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )    
            return [('id', 'in', [])]
        else:
            if value is False:
                value = 0
            id_list = []
            partners = self.env['res.partner'].search([])
            for partner in partners:
                if operator == '=' and partner.slate_balance == value: id_list.append(partner.id)
                if operator == '!=' and partner.slate_balance != value: id_list.append(partner.id)
                if operator == '<' and partner.slate_balance < value: id_list.append(partner.id)
                if operator == '<=' and partner.slate_balance <= value: id_list.append(partner.id)
                if operator == '>' and partner.slate_balance > value: id_list.append(partner.id)
                if operator == '>=' and partner.slate_balance >= value: id_list.append(partner.id)
            return [('id', 'in', id_list)]

    def search_by_last_fund_date(self, operator, value):
        _logger.info('Searching slate fund date with: %s and value %s', operator, value)
        if operator not in ('=', '!=', '<', '<=', '>', '>='):
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )    
            return [('id', 'in', [])]
        else:
            if value is False:
                value = 0
            id_list = []
            partners = self.env['res.partner'].search([])
            for partner in partners:
                if operator == '=' and partner.slate_last_fund_date == value: id_list.append(partner.id)
                if operator == '!=' and partner.slate_last_fund_date != value: id_list.append(partner.id)
                if operator == '<' and partner.slate_last_fund_date < value: id_list.append(partner.id)
                if operator == '<=' and partner.slate_last_fund_date <= value: id_list.append(partner.id)
                if operator == '>' and partner.slate_last_fund_date > value: id_list.append(partner.id)
                if operator == '>=' and partner.slate_last_fund_date >= value: id_list.append(partner.id)
            return [('id', 'in', id_list)]

    def search_by_last_pay_date(self, operator, value):
        _logger.info('Searching slate pay date with: %s and value %s', operator, value)
        if operator not in ('=', '!=', '<', '<=', '>', '>='):
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )    
            return [('id', 'in', [])]
        else:
            if value is False:
                value = 0
            id_list = []
            partners = self.env['res.partner'].search([])
            for partner in partners:
                if operator == '=' and partner.slate_last_pay_date == value: id_list.append(partner.id)
                if operator == '!=' and partner.slate_last_pay_date != value: id_list.append(partner.id)
                if operator == '<' and partner.slate_last_pay_date < value: id_list.append(partner.id)
                if operator == '<=' and partner.slate_last_pay_date <= value: id_list.append(partner.id)
                if operator == '>' and partner.slate_last_pay_date > value: id_list.append(partner.id)
                if operator == '>=' and partner.slate_last_pay_date >= value: id_list.append(partner.id)
            return [('id', 'in', id_list)]

    def search_by_last_msg_date(self, operator, value):
        _logger.info('Searching slate message date with: %s and value %s', operator, value)
        if operator not in ('=', '!=', '<', '<=', '>', '>='):
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )    
            return [('id', 'in', [])]
        else:
            if value is False:
                value = 0
            id_list = []
            partners = self.env['res.partner'].search([])
            for partner in partners:
                if operator == '=' and partner.last_msg_date == value: id_list.append(partner.id)
                if operator == '!=' and partner.last_msg_date != value: id_list.append(partner.id)
                if operator == '<' and partner.last_msg_date < value: id_list.append(partner.id)
                if operator == '<=' and partner.last_msg_date <= value: id_list.append(partner.id)
                if operator == '>' and partner.last_msg_date > value: id_list.append(partner.id)
                if operator == '>=' and partner.last_msg_date >= value: id_list.append(partner.id)
            return [('id', 'in', id_list)]

    @api.one
    def set_access_for_slate_number(self):
        self.able_to_modify_slate_number = self.env['res.users'].has_group('logisfloo_base.group_logisfloo_admin')
    
    @api.onchange('first_name', 'last_name')
    def _on_change_name(self):
        if self.first_name:
            self.first_name=self.first_name.strip()
        if self.last_name:
            self.last_name=self.last_name.strip()
        self.name = concat_names(self.first_name, self.last_name)
        
    @api.noguess
    def _auto_init(self, cr, context=None):
        res = super(Partner, self)._auto_init(cr, context=context)
        cr.execute("UPDATE res_partner set last_name = name where last_name IS NULL")
        return res

    @api.one
    def get_slate_balance(self):
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', 'in', self.slate_partners.ids)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        self.slate_balance = round(credit - debit, 2) 

    @api.one
    def get_slate_last_fund_date(self):
        account_id = self.property_account_slate_id.id
        move_line = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', 'in', self.slate_partners.ids),('credit','>',0)],order='date desc', limit=1)
        self.slate_last_fund_date = move_line.date 

    @api.one
    def get_slate_last_pay_date(self):
        account_id = self.property_account_slate_id.id
        move_line = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', 'in', self.slate_partners.ids),('debit','>',0)],order='date desc', limit=1)
        self.slate_last_pay_date = move_line.date 

    @api.one
    def get_last_msg_date(self):
        last_mail_message = self.env['mail.message'].search([('model', '=', 'res.partner'), ('res_id', '=', self.id), ('author_id', '=', self.id)],order='date desc', limit=1)
        self.last_msg_date = last_mail_message.date 

    @api.model
    def _cron_negative_slate_warning(self):
        _logger.info('negative slate warning')
        partners = self.env['res.partner'] 
        for partner in partners.search([('slate_balance', '<', 0), ('active', '=',True), ('customer', '=',True)]):
            if partner.email:
                template = self.env.ref('logisfloo_base.email_slate_warning')
                self.env['mail.template'].browse(template.id).send_mail(partner.id)
            else:
                notifyteam=True
                for sibling in partner.slate_partners:
                    if sibling.email:
                        notifyteam=False
                if notifyteam:
                    # Cannot contact any slate member by mail, send notification to team
                    template = self.env.ref('logisfloo_base.email_slate_warning_nocontact')
                    self.env['mail.template'].browse(template.id).send_mail(partner.id)

    @api.one
    def send_welcome_email(self):
        _logger.info('Send welcome email')
        template = self.env.ref('logisfloo_base.welcome_email')
        self.env['mail.template'].browse(template.id).send_mail(self.id)
        self.welcome_email=True

    # Send update email -> should be an option on the form when updating
    
    # Send contact details vérification email to all clients in one go -> to be used as automated action
    # pas nécéssaire car les données sont sur le ticket de caisse !!!!
                        
    @api.one
    def get_slate_partners(self):
        # If slate number is 0, then this is not a slate and there is no partners
        if self.slate_number != 0:
            partners = self.env['res.partner']
            domain=[('slate_number', '=',self.slate_number)]
            self.slate_partners = partners.search(domain)

    def get_slate_partner_ids(self):
        return str([partner.id for partner in self.slate_partners if partner.email]).replace('[', '').replace(']', '') 

    def get_unrec_paid_pos_order_amount(self):
        paid_amount=0
        pos_orders= self.env['pos.order'].search([('partner_id', 'in', self.slate_partners.ids),('state','=','paid')])
        for pos_order in pos_orders:
            paid_amount=paid_amount+pos_order.amount_total
        return paid_amount

    def get_last_subscription_payment(self):
        result={'date':"Aucun", 'credit':0}  
        subscription_account_id = self.env.ref('logisfloo_base.a705010').id
        subscription_product_id = self.env['product.product'].search([('name_template', '=', 'Cotisation Mensuelle'),('active','=',True)]).id
        move_line=self.env['account.move.line'].search([('partner_id', 'in', self.slate_partners.ids),('account_id','=',subscription_account_id),('credit','>',0)],order='date desc', limit=1)
        if move_line.id:
            result={'date':move_line.date, 'credit':move_line.credit}
        # We also need to check if there is one or more in the unreconciled purchases.
        # We could have looked only at the pos_orders, but scanning through all the lines is ineficient.
        # This is particularly the case when no subscription has been paid yet has all the lines of all teh orders would have to be scanned.
        pos_orders= self.env['pos.order'].search([('partner_id', 'in', self.slate_partners.ids),('state','=','paid')],order='date_order asc')
        for pos_order in pos_orders:
            for line in pos_order.lines:
                if line.product_id.id==subscription_product_id:
                    date=datetime.datetime.strptime(pos_order.date_order,'%Y-%m-%d %H:%M:%S').date()
                    result={'date':date, 'credit':line.price_subtotal_incl}   
        return [result['date'], result['credit']]

    @api.one
    def get_balance_and_eater(self):
        self.ensure_one()
        self = self.sudo()
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', 'in', self.slate_partners.ids)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        return str(credit - debit - self.get_unrec_paid_pos_order_amount())
    
    @api.multi
    def show_slate_move_lines(self):
        ctx={}
        ctx.update({
            'search_default_account_id': self.property_account_slate_id.id,
        })
        return { 
            'res_model': 'account.move.line',
            'src_model': 'res.partner',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain' : [['partner_id', 'in', self.slate_partners.ids]], 
            'context': ctx,
        }

class LogisflooSetSlateNumberWizard(models.TransientModel):
    _name = 'logisfloo.setslatenumber.wizard'

    @api.multi
    def dont_close_form(self):
        self.ensure_one()
        return {"type": "set_scrollTop",}
                
    @api.multi
    def set_slate_number(self):
        thispartner=self.env['res.partner'].browse(self.env.context.get('active_id'))
        thispartner.slate_number = self.first_partner.slate_number
                    
    first_partner= fields.Many2one('res.partner', string='First Partner', change_default=True,
        required=True, track_visibility='always')
    
class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    @api.model
    def set_account_holder(self):
        AnonymousBankAccount=self.env['res.partner.bank'].search([('partner_id', '=', False)])
        for account in AnonymousBankAccount:
            stmntline=self.env['account.bank.statement.line'].search([('bank_account_id','=',account.id)],order='date desc', limit=1)
            if stmntline.partner_id:
                account.partner_id=stmntline.partner_id

class LogisflooEmailWizard(models.TransientModel):
    _name = 'logisfloo.email.wizard'

    yes_no = fields.Char(default='Do you want to proceed?')

    @api.multi
    def yes(self):
        self.env['res.partner'].browse(self.env.context.get('active_id')).send_welcome_email()

    @api.multi
    def no(self):
        pass # don't do anything stupid
    