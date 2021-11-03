# -*- coding: utf-8 -*-
from openerp import models, fields, api, _

import logging
_logger = logging.getLogger(__name__)


class LogisflooPosOrder(models.Model):

    _inherit = 'pos.order'

    @api.model
    def send_order(self, receipt_name):
        order = self.search([('pos_reference', '=', receipt_name)])
        if not order:
            return _('Error: no order found')
        if not order.partner_id.get_slate_partner_ids():
            return _('Cannot send the ticket, no email address found on the client')
        mail_template = self.env.ref("logisfloo_base.email_send_ticket")
        mail_template.send_mail(order.id)
        return _("Ticket sent")

    @api.model
    def create_from_ui(self, orders):
        # send the ticket right after creating the order (no need to request to send the ticket on the GUI)
        order_ids = super(LogisflooPosOrder,self).create_from_ui(orders)
        mail_template = self.env.ref("logisfloo_base.email_send_ticket")
        for order_id in order_ids:
            order_item = self.search([('id', '=', order_id)])
            if order_item.partner_id.get_slate_partner_ids():
                mail_template.send_mail(order_item.id)
        return order_ids

    @api.model
    def _process_order(self, order):
        lines = order['lines']
        order['lines'] = [l for l in lines if l[2]['qty'] !=0]
                
        return super(LogisflooPosOrder, self)._process_order(order)

class LogisflooPosSession(models.Model):

    _inherit = 'pos.session'

    def _confirm_orders(self, cr, uid, ids, context=None):
        for session in self.browse(cr, uid, ids, context=context):
            for order in session.order_ids:
                # FIX POS cannot be closed bacause of unpaid orders
                # Delete unpaid orders with no actual purchase - this is a side effect of people checking their slate amount on a separate POS tab
                if order.state not in ('paid', 'invoiced') and len(order.lines) == 0:
                    order.unlink()

        return super(LogisflooPosSession, self)._confirm_orders(cr, uid, ids, context=None)
