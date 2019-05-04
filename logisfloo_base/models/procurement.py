from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError
from openerp import exceptions
from datetime import datetime

import logging
_logger = logging.getLogger(__name__)


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    @api.model
    def _check(self, procurement):
        _logger.info('$$$$$$$ procurement _check in logisfloo')
        if procurement.purchase_line_id:
            _logger.info('$$$$$$$ purchase_line_id')
            if not procurement.move_ids:
                return False
            _logger.info('$$$$$$$ computing: %s', str(all(move.state in ('done', 'cancel') for move in procurement.move_ids)))
            return all(move.state in ('done', 'cancel') for move in procurement.move_ids)
        return super(ProcurementOrder, self)._check(procurement)
    
    @api.model
    def _cron_check(self):
        _logger.info('procurement automated _check')
        procorders = self.env['procurement.order'] 
        for procorder in procorders.search([('state', '=','running')]):
            procorder.check()
            #super(ProcurementOrder, self)._check(procorder)


