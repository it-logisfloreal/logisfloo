from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError

class LogisflooPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    
    discount = fields.Float(string='Discount')

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            taxes = line.taxes_id.compute_all(line.price_unit * (1-(line.discount or 0.0) / 100.0), line.order_id.currency_id, line.product_qty, product=line.product_id, partner=line.order_id.partner_id)
            line.update({
                'price_tax': taxes['total_included'] - taxes['total_excluded'],
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    def _get_seller_discount(self):
        if not self.product_id:
            return 
        seller = self.product_id._select_seller(
            self.product_id,
            partner_id=self.partner_id,
            quantity=self.product_qty,
            date=self.order_id.date_order and self.order_id.date_order[:10],
            uom_id=self.product_uom)
        if not seller:
            return 
        return seller.discount
    
    # Override the PO line onchange quantity method to update the seller discount on the PO line
    def _onchange_quantity(self):
        super(LogisflooPurchaseOrderLine,self)._onchange_quantity()
        self.discount = self._get_seller_discount()

    # Override the PO line create method to add the seller discount on the PO line
    @api.model
    def create(self, values):
        record = super(LogisflooPurchaseOrderLine,self).create(values)
        record['discount'] = record._get_seller_discount()
        return record
    
class LogisflooAccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _prepare_invoice_line_from_po_line(self, line):
        data=super(LogisflooAccountInvoice,self)._prepare_invoice_line_from_po_line(line)
        data['discount'] = line.discount or 0.0
        return data