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

    @api.multi
    def get_move_lines_for_reconciliation_widget(self, excluded_ids=None, strparam=False, offset=0, limit=None):
        """ Returns move lines for the bank statement reconciliation widget, formatted as a list of dicts
        """
        property_account_slate_id = self.env['ir.property'].search([('name', '=', 'property_account_slate_id')], limit=1)
        _logger.info('property values %s',str(property_account_slate_id.id))
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