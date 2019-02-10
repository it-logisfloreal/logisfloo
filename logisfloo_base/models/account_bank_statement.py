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


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def process_reconciliation(self, counterpart_aml_dicts=None, payment_aml_rec=None, new_aml_dicts=None):
        _logger.info('Processing Reconciliation ************')
        property_account_slate_id = self.env['ir.property'].search([('name', '=', 'property_account_slate_id')], limit=1)
        slate_account_id = self.env['account.account'].search([('id', '=',property_account_slate_id.value_reference.split(',')[1])])
        counterpart_moves = super(AccountBankStatementLine,self).process_reconciliation(counterpart_aml_dicts,payment_aml_rec,new_aml_dicts)
        for move in counterpart_moves:
            for aline in move.line_ids:
                _logger.info('Processing line for account %s',aline.account_id.name)
                if aline.account_id == slate_account_id:
                    _logger.info('Ardoise line ########')
                    _logger.info(' for %s', aline.partner_id.name)

    @api.multi
    def temp_get_move_lines_for_reconciliation_widget(self, excluded_ids=None, strparam=False, offset=0, limit=None):
        """ Returns move lines for the bank statement reconciliation widget, formatted as a list of dicts
        """
        property_account_slate_id = self.env['ir.property'].search([('name', '=', 'property_account_slate_id')], limit=1)
        _logger.info('property values %s',str(property_account_slate_id.id))
        # this one gives the id of the property ... not the account id !
        aml_recs = self.get_move_lines_for_reconciliation(excluded_ids=excluded_ids, 
                                                          str=strparam, 
                                                          offset=offset, 
                                                          limit=limit, 
                                                          additional_domain=[('account_id', '=', 0)])
        target_currency = self.currency_id or self.journal_id.currency_id or self.journal_id.company_id.currency_id
        return aml_recs.prepare_move_lines_for_reconciliation_widget(target_currency=target_currency, target_date=self.date)

    @api.multi
    def get_move_lines_for_reconciliation_widget2(self, excluded_ids=None, strparam=False, offset=0, limit=None):
        
        dummypartner=self.env['res.partner']
        _logger.info('property values %d',dummypartner.property_account_slate_id.id)
        #excluded_ids.append(dummypartner.property_account_slate_id.id)
        excluded_ids.append(185)
        mystring=str(excluded_ids).strip('[]')
        _logger.info('Excluded ids %s',mystring)
        return super(AccountBankStatementLine,self).get_move_lines_for_reconciliation_widget(excluded_ids, strparam, offset, limit)