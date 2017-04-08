# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from openerp.addons.beesdoo_base.tools import concat_names

class Partner(models.Model):

    _inherit = 'res.partner'

    slate_number = fields.Integer('Slate Number')
    subscription_date = fields.Date('Subscription Date')
    subscription_event = fields.Char('Subscription Event', size=40)
    floreal_logis_membership = fields.Selection([('logis', 'Logis'),('floréal','Floréal')], string="Tenant Logis/Floréal")
    add_to_mailing_list = fields.Boolean('Add to Mailing List')
    slate_balance = fields.Monetary(string='Slate Balance', compute='_slate_balance_get')   
    property_account_slate_id = fields.Many2one(
        'account.account', 
        company_dependent=True,
        string="Slate Account", 
        domain="[('deprecated', '=', False)]",
        help="This account will be used as the pre-paid slate account for the current partner",
        required=True)
    
    @api.one
    def _slate_balance_get(self):
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', '=', self.id)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        self.slate_balance = round(credit - debit, 2) 
                    
    @api.multi
    def get_balance_and_eater(self):
        self.ensure_one()
        self = self.sudo()
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', '=', self.id)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        eater1, eater2 = self._get_eater()
        return str(round(credit - debit, 2)), eater1, eater2
 
        