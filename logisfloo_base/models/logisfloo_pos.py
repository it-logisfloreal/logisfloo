# -*- coding: utf-8 -*-
from openerp import models, fields, api, _

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
