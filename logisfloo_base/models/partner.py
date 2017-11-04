# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from openerp.addons.logisfloo_base.tools import concat_names


class Partner(models.Model):

    _inherit = 'res.partner'

    first_name = fields.Char('First Name')
#    last_name = fields.Char('Last Name')
#    prefered to use the definition from the pos
    last_name = fields.Char('Last Name', required=True, default="/")

    slate_number = fields.Integer('Slate Number')
    subscription_date = fields.Date('Subscription Date')
    subscription_event = fields.Char('Subscription Event', size=40)
    floreal_logis_membership = fields.Selection([('logis', 'Logis'),('floreal','Floréal')], string="Tenant Logis/Floréal")
    add_to_mailing_list = fields.Boolean('Add to Mailing List')
    slate_balance = fields.Monetary(string='Slate Balance', compute='_slate_balance_get')   
    property_account_slate_id = fields.Many2one(
        'account.account', 
        company_dependent=True,
        string="Slate Account", 
        domain="[('deprecated', '=', False)]",
        help="This account will be used as the pre-paid slate account for the current partner",
        required=True)
    
    @api.onchange('first_name', 'last_name')
    def _on_change_name(self):
        self.name = concat_names(self.first_name, self.last_name)

    @api.noguess
    def _auto_init(self, cr, context=None):
        res = super(Partner, self)._auto_init(cr, context=context)
        cr.execute("UPDATE res_partner set last_name = name where last_name IS NULL")
        return res

    @api.one
    def _slate_balance_get(self):
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', '=', self.id)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        self.slate_balance = round(credit - debit, 2) 
                    
    @api.one
    def get_balance_and_eater(self):
        self.ensure_one()
        self = self.sudo()
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', '=', self.id)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        return str(round(credit - debit, 2))   
 
        
