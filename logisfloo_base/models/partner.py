# -*- coding: utf-8 -*-
#import logging
#from openerp.osv import orm

from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from openerp.addons.logisfloo_base.tools import concat_names

#_logger = logging.getLogger(__name__)

class Partner(models.Model):

    _inherit = 'res.partner'

    first_name = fields.Char('First Name')
    last_name = fields.Char('Last Name', required=True, default="/")
    slate_number = fields.Integer('Slate Number')
    subscription_date = fields.Date('Subscription Date')
    subscription_event = fields.Char('Subscription Event', size=40)
    floreal_logis_membership = fields.Selection([('logis', 'Logis'),('floreal','Floréal')], string="Tenant Logis/Floréal")
    add_to_mailing_list = fields.Boolean('Add to Mailing List')
    slate_balance = fields.Monetary(string='Slate Balance', compute='get_slate_balance')  
    slate_partners = fields.One2many("res.partner", "slate_number", domain=[],compute='get_slate_partners')   
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
    
    @api.onchange('first_name', 'last_name')
    def _on_change_name(self):
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
    def get_slate_partners(self):
        # If slate number is 0, then this is not a slate and there is no partners
        if self.slate_number != 0:
            partners = self.env['res.partner']
            domain=[('slate_number', '=',self.slate_number)]
            self.slate_partners = partners.search(domain)

    @api.one
    def get_balance_and_eater(self):
        self.ensure_one()
        self = self.sudo()
        account_id = self.property_account_slate_id.id
        move_lines = self.env['account.move.line'].search([('account_id', '=', account_id), ('partner_id', 'in', self.slate_partners.ids)])
        credit = sum([m.credit for m in move_lines])
        debit = sum([m.debit for m in move_lines])
        return str(round(credit - debit, 2))   
    
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
