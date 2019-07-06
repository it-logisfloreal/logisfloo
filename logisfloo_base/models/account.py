# -*- coding: utf-8 -*-

from openerp import api, fields, models, _
from openerp.osv import expression
from openerp.tools import float_is_zero
from openerp.tools import float_compare, float_round
from openerp.tools.misc import formatLang
from openerp.exceptions import UserError, ValidationError

import time
import math
import string

import logging
_logger = logging.getLogger(__name__)

class LogisflooChangeAccountWizard(models.TransientModel):
    _name = 'logisfloo.changeaccount.wizard'

    @api.multi
    def update(self):
        move_lines = self.env['account.move.line'].browse(self._context.get('active_ids', []))
        
        for ml in move_lines:
            move = self.env['account.move'].create({
                'journal_id': self.journal_id.id,
                'company_id': self.env.user.company_id.id,
                'date': ml.date,
                'narration': self.narration,
            })
            mvml = self.env['account.move.line'].with_context(check_move_validity=False).create({
                'name': ml.name,
                'ref': ml.ref,
                'partner_id':ml.partner_id.id,
                'journal_id':move.journal_id.id,
                'date': ml.date,
                'account_id':self.destination_account.id,
                'debit':ml.debit,
                'credit':ml.credit,
                'quantity': ml.quantity,
                'move_id': move.id,
                'statement_id': ml.statement_id.id,
                'date_maturity': ml.date_maturity,            
                })
            newml = self.env['account.move.line'].with_context(check_move_validity=False).create({
                'name': ml.name,
                'ref': ml.ref,
                'partner_id':ml.partner_id.id,
                'journal_id':move.journal_id.id,
                'date': ml.date,
                'account_id':ml.account_id.id,
                'debit':ml.credit,
                'credit':ml.debit,
                'quantity': ml.quantity,
                'move_id': move.id,
                'statement_id': ml.statement_id.id,
                'date_maturity': ml.date_maturity,            
                })
                        

    @api.multi
    def _get_default_journal(self):
        return self.env['account.journal'].search([('code', '=', 'OD')], limit=1).id

    narration = fields.Text(string='Internal Note')
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, default=_get_default_journal)
    destination_account = fields.Many2one(
        'account.account', 
        company_dependent=True,
        string="Destination Account", 
        domain="[('deprecated', '=', False)]",
        help="This account is the destination account.",
        required=True)    
    