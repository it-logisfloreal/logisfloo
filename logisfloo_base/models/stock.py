 # -*- coding: utf-8 -*-
import logging
import math
import time
import openerp.addons.decimal_precision as dp

from datetime import date, datetime, timedelta
from dateutil import relativedelta
from openerp import SUPERUSER_ID, models, fields, api
from openerp.tools.float_utils import float_compare, float_round
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from openerp.exceptions import UserError

_logger = logging.getLogger(__name__)

class LogisflooStockMove(models.Model):
    _inherit = 'stock.move'

    # replace original function to correct bug when move quantity = 0, as this can happen with POS orders

    def action_done(self, cr, uid, ids, context=None):
        """ Process completely the moves given as ids and if all moves are done, it will finish the picking.
        """
        context = context or {}
        picking_obj = self.pool.get("stock.picking")
        quant_obj = self.pool.get("stock.quant")
        uom_obj = self.pool.get("product.uom")
        todo = [move.id for move in self.browse(cr, uid, ids, context=context) if move.state == "draft"]
        if todo:
            ids = self.action_confirm(cr, uid, todo, context=context)
        pickings = set()
        procurement_ids = set()
        #Search operations that are linked to the moves
        operations = set()
        move_qty = {}
        for move in self.browse(cr, uid, ids, context=context):
            if move.picking_id:
                pickings.add(move.picking_id.id)
            move_qty[move.id] = move.product_qty
            for link in move.linked_move_operation_ids:
                operations.add(link.operation_id)

        #Sort operations according to entire packages first, then package + lot, package only, lot only
        operations = list(operations)
        operations.sort(key=lambda x: ((x.package_id and not x.product_id) and -4 or 0) + (x.package_id and -2 or 0) + (x.pack_lot_ids and -1 or 0))

        for ops in operations:
            if ops.picking_id:
                pickings.add(ops.picking_id.id)
            entire_pack=False
            if ops.product_id:
                #If a product is given, the result is always put immediately in the result package (if it is False, they are without package)
                quant_dest_package_id  = ops.result_package_id.id
            else:
                # When a pack is moved entirely, the quants should not be written anything for the destination package
                quant_dest_package_id = False
                entire_pack=True
            lot_qty = {}
            tot_qty = 0.0
            for pack_lot in ops.pack_lot_ids:
                qty = uom_obj._compute_qty(cr, uid, ops.product_uom_id.id, pack_lot.qty, ops.product_id.uom_id.id)
                lot_qty[pack_lot.lot_id.id] = qty
                tot_qty += pack_lot.qty
            if ops.pack_lot_ids and ops.product_id and float_compare(tot_qty, ops.product_qty, precision_rounding=ops.product_uom_id.rounding) != 0.0:
                raise UserError(_('You have a difference between the quantity on the operation and the quantities specified for the lots. '))

            quants_taken = []
            false_quants = []
            lot_move_qty = {}
            #Group links by move first
            move_qty_ops = {}
            for record in ops.linked_move_operation_ids:
                move = record.move_id
                if not move_qty_ops.get(move):
                    move_qty_ops[move] = record.qty
                else:
                    move_qty_ops[move] += record.qty
            #Process every move only once for every pack operation
            for move in move_qty_ops:
                main_domain = [('qty', '>', 0)]
                self.check_tracking(cr, uid, move, ops, context=context)
                preferred_domain = [('reservation_id', '=', move.id)]
                fallback_domain = [('reservation_id', '=', False)]
                fallback_domain2 = ['&', ('reservation_id', '!=', move.id), ('reservation_id', '!=', False)]
                if not ops.pack_lot_ids:
                    preferred_domain_list = [preferred_domain] + [fallback_domain] + [fallback_domain2]
                    quants = quant_obj.quants_get_preferred_domain(cr, uid, move_qty_ops[move], move, ops=ops, domain=main_domain,
                                                        preferred_domain_list=preferred_domain_list, context=context)
                    quant_obj.quants_move(cr, uid, quants, move, ops.location_dest_id, location_from=ops.location_id,
                                            lot_id=False, owner_id=ops.owner_id.id, src_package_id=ops.package_id.id,
                                            dest_package_id=quant_dest_package_id, entire_pack=entire_pack, context=context)
                else:
                    # Check what you can do with reserved quants already
                    qty_on_link = move_qty_ops[move]
                    rounding = ops.product_id.uom_id.rounding
                    for reserved_quant in move.reserved_quant_ids:
                        if (reserved_quant.owner_id.id != ops.owner_id.id) or (reserved_quant.location_id.id != ops.location_id.id) or \
                                (reserved_quant.package_id.id != ops.package_id.id):
                            continue
                        if not reserved_quant.lot_id:
                            false_quants += [reserved_quant]
                        elif float_compare(lot_qty.get(reserved_quant.lot_id.id, 0), 0, precision_rounding=rounding) > 0:
                            if float_compare(lot_qty[reserved_quant.lot_id.id], reserved_quant.qty, precision_rounding=rounding) >= 0:
                                lot_qty[reserved_quant.lot_id.id] -= reserved_quant.qty
                                quants_taken += [(reserved_quant, reserved_quant.qty)]
                                qty_on_link -= reserved_quant.qty
                            else:
                                quants_taken += [(reserved_quant, lot_qty[reserved_quant.lot_id.id])]
                                lot_qty[reserved_quant.lot_id.id] = 0
                                qty_on_link -= lot_qty[reserved_quant.lot_id.id]
                    lot_move_qty[move.id] = qty_on_link

                # This is the corrected bug, only raise the UserError if the qty is not null 
                if move.product_uom_qty != 0 and not move_qty.get(move.id):
                    raise UserError(_("The roundings of your Unit of Measures %s on the move vs. %s on the product don't allow to do these operations or you are not transferring the picking at once. Product %s, qty %f") % (move.product_uom.name, move.product_id.uom_id.name, move.product_id.name, move.product_uom_qty))
                move_qty[move.id] -= move_qty_ops[move]

            #Handle lots separately
            if ops.pack_lot_ids:
                self._move_quants_by_lot(cr, uid, ops, lot_qty, quants_taken, false_quants, lot_move_qty, quant_dest_package_id, context=context)

            # Handle pack in pack
            if not ops.product_id and ops.package_id and ops.result_package_id.id != ops.package_id.parent_id.id:
                self.pool.get('stock.quant.package').write(cr, SUPERUSER_ID, [ops.package_id.id], {'parent_id': ops.result_package_id.id}, context=context)
        #Check for remaining qtys and unreserve/check move_dest_id in
        move_dest_ids = set()
        for move in self.browse(cr, uid, ids, context=context):
            move_qty_cmp = float_compare(move_qty[move.id], 0, precision_rounding=move.product_id.uom_id.rounding)
            if move_qty_cmp > 0:  # (=In case no pack operations in picking)
                main_domain = [('qty', '>', 0)]
                preferred_domain = [('reservation_id', '=', move.id)]
                fallback_domain = [('reservation_id', '=', False)]
                fallback_domain2 = ['&', ('reservation_id', '!=', move.id), ('reservation_id', '!=', False)]
                preferred_domain_list = [preferred_domain] + [fallback_domain] + [fallback_domain2]
                self.check_tracking(cr, uid, move, False, context=context)
                qty = move_qty[move.id]
                quants = quant_obj.quants_get_preferred_domain(cr, uid, qty, move, domain=main_domain, preferred_domain_list=preferred_domain_list, context=context)
                quant_obj.quants_move(cr, uid, quants, move, move.location_dest_id, lot_id=move.restrict_lot_id.id, owner_id=move.restrict_partner_id.id, context=context)

            # If the move has a destination, add it to the list to reserve
            if move.move_dest_id and move.move_dest_id.state in ('waiting', 'confirmed'):
                move_dest_ids.add(move.move_dest_id.id)

            if move.procurement_id:
                procurement_ids.add(move.procurement_id.id)

            #unreserve the quants and make them available for other operations/moves
            quant_obj.quants_unreserve(cr, uid, move, context=context)
        # Check the packages have been placed in the correct locations
        self._check_package_from_moves(cr, uid, ids, context=context)
        #set the move as done
        self.write(cr, uid, ids, {'state': 'done', 'date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)}, context=context)
        self.pool.get('procurement.order').check(cr, uid, list(procurement_ids), context=context)
        #assign destination moves
        if move_dest_ids:
            self.action_assign(cr, uid, list(move_dest_ids), context=context)
        #check picking state to set the date_done is needed
        done_picking = []
        for picking in picking_obj.browse(cr, uid, list(pickings), context=context):
            if picking.state == 'done' and not picking.date_done:
                done_picking.append(picking.id)
        if done_picking:
            picking_obj.write(cr, uid, done_picking, {'date_done': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)}, context=context)
        return True

class LogisflooStockInventory(models.Model):
    _inherit = "stock.inventory"

    @api.multi
    def force_to_accounting_date(self):
        # Forces all dates in records related to this inventory to the accounting date
        # Set the time to 23h 59min 55sec CET time -> 21h for UTC in summer time (time is stored in DB in UTC)
        new_datetime = datetime.strptime(self.accounting_date, DEFAULT_SERVER_DATE_FORMAT) + timedelta(hours=21, minutes=59, seconds=55)
        moves=self.env['stock.move'].search([('inventory_id','=',self.id)])
        for move in moves:
            move.date = new_datetime
            move.date_expected = new_datetime
        self.date = new_datetime

class LogisflooInventoryPeriod(models.Model):
    _description = 'Inventory Period'
    _name = "logisfloo.inventory.period"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'name asc'

    name = fields.Char('Period name', required=True, index=True, copy=False, default='New')
    datefrom = fields.Datetime(string='Start', readonly=True, states={'open': [('readonly', False)]}, 
                           default=datetime.now(),
                           index=True, track_visibility='onchange', help="Keep empty to use the current date")
    dateto = fields.Datetime(string='End', readonly=True, states={'open': [('readonly', False)]}, 
                           default=datetime.now(),
                           index=True, track_visibility='onchange', help="Keep empty to use the current date")
    previous_period = fields.Many2one('logisfloo.inventory.period', string='Previous period', track_visibility='onchange')
    inventory_adj_ids = fields.Many2many('stock.inventory', 'id', string='Inventory Adjustments', track_visibility='onchange')
    state = fields.Selection([
            ('open', 'Open'),
            ('closed', 'Closed'),
        ], string='Status', index=True, readonly=True, default='open', track_visibility='onchange', help="")

    @api.multi
    def button_close(self):
        self.write({'state': 'closed'})
        return {}

    @api.multi
    def button_reopen(self):
        self.write({'state': 'open'})
        return {}

    @api.multi
    def show_period_report(self):
        ctx={}
        return { 
            'res_model': 'logisfloo.inventory.reportline',
            'src_model': 'logisfloo.inventory.period',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain' : [['inventory_period_id', '=', self.id]], 
            'context': ctx,
        }

    @api.model
    def rebuild_all_inventory_reports(self):
        periods = self.env['logisfloo.inventory.period'].search([('state', '=', 'open')])
        for period in periods:
            period.rebuild_inventory_report()

    @api.multi
    def rebuild_inventory_report(self):
        def get_product_cost_at_date(product_id, date):
            return (self.env['product.price.history'].search([('product_id', '=', product_id),('datetime', '>=', date)],limit=1,order='datetime asc').cost 
                    or self.env['product.price.history'].search([('product_id', '=', product_id),('datetime', '<', date)],limit=1,order='datetime desc').cost 
                    or 0.0)
        
        def init_product_data(product_id):
            return {
                    'product_id': product_id,
                    'movecount': 0.0,
                    'startqty': 0.0,
                    'endqty': 0.0,
                    'soldqty': 0.0,
                    'boughtqty': 0.0,
                    'lossqty': 0.0,
                    'extraqty': 0.0,
                    'corrqty': 0.0,
                    'unknownqty': 0.0,
                    'bought_value': 0.0,
                    'invoiced_value': 0.0,
                    'sold_value': 0.0,
                    'sold_value_period': 0.0,
                    'sold_cost_period': 0.0,
                    'sold_value_latest': 0.0,
                    'sold_cost_latest': 0.0,
                    'corr_value': 0.0,
                    'sold_purchase_value': 0.0,
                    'sold_iqty': 0.0,
                    'bought_iqty': 0.0,
                    'invqty': 0.0,
                    'diffqty': 0.0,
                    'inv_value': 0.0,
                }

        _logger.info('Rebuild inventory report for period %s', self.name)
        loc_loss = self.env['stock.location'].search([('id', '=', 5)]).id
        loc_vendor = self.env['stock.location'].search([('id', '=', 8)]).id
        loc_customer = self.env['stock.location'].search([('id', '=', 9)]).id
        loc_stock = self.env['stock.location'].search([('id', '=', 19)]).id
        move_recs = self.env['stock.move'].search([('state', '=', 'done'),('date', '>=', self.datefrom), ('date', '<=', self.dateto)]
                                ,order='product_id asc, date asc')
        inventory_lines = self.env['stock.inventory.line']
        reportline = self.env['logisfloo.inventory.reportline']
        reportline.search([('inventory_period_id', '=', self.id)]).unlink()
        data_items = []
        product_data = {}
        current_product_id = 0

        for move in move_recs:
            if move.product_id != current_product_id:
                if current_product_id != 0:
                    data_items.append(product_data)
                current_product_id = move.product_id
                product_data = init_product_data(current_product_id.id)

            product_data['movecount'] += 1   # count the number of moves used to build this, so we can do some checks ...
            if move.location_id.id == loc_loss and move.location_dest_id.id == loc_stock:
                # loss to stock -> extraqty -= qty
                product_data['extraqty'] += move.product_qty
            elif move.location_id.id == loc_vendor and move.location_dest_id.id == loc_stock:
                # bought -> boughtqty += qty
                product_data['boughtqty'] += move.product_qty
                product_data['bought_value'] += move.product_qty * get_product_cost_at_date(move.product_id.id, move.date)
            elif move.location_id.id == loc_customer and move.location_dest_id.id == loc_stock:
                # returned / tare -> soldqty -= qty
                product_data['soldqty'] -= move.product_qty
            elif move.location_id.id == loc_stock and move.location_dest_id.id == loc_loss:
                # loss -> lossqty += qty
                product_data['lossqty'] += move.product_qty
            elif move.location_id.id == loc_stock and move.location_dest_id.id == loc_vendor:
                # returned to vendor -> boughtqty -= qty
                product_data['boughtqty'] -= move.product_qty
                product_data['bought_value'] -= move.product_qty * get_product_cost_at_date(move.product_id.id, move.date)
            elif move.location_id.id == loc_stock and move.location_dest_id.id == loc_customer:
                # sold -> soldqty += qty
                product_data['soldqty'] += move.product_qty
            else:
                # unknown
                product_data['unknownqty'] += move.product_qty
        
        data_items.append(product_data)

        # Add products for which there has been no move, but for which we have a stock (previous period end qty != 0)
        prev_period_product_ids = self.env['logisfloo.inventory.reportline'].search([
                                    ('inventory_period_id', '=', self.previous_period.id), 
                                    ('endqty','!=',0.0)
                                    ])
        prev_period_product_ids = [x.product_id.id for x in prev_period_product_ids]
        this_period_product_ids = [x['product_id'] for x in data_items]
        missing_product_ids = [x for x in prev_period_product_ids if x not in this_period_product_ids]
        for product_id in missing_product_ids:
            data_items.append(init_product_data(product_id))
        
        for item in data_items:
            product = self.env['product.product'].with_context(active_test=False).search([('id', '=', item['product_id'])])
            template = self.env['product.template'].with_context(active_test=False).search([('id', '=', product.product_tmpl_id.id)])

            # Skip any item that is not a product (e.g. service)
            if template.type != 'product':
                continue

            # Add Quantity found during inventory
            inv_ids = [x.id for x in self.inventory_adj_ids]
            item['invqty'] = inventory_lines.search([('inventory_id', 'in', inv_ids),('product_id', '=', item['product_id'])]
                                    ,order='product_id asc, write_date desc', limit = 1).product_qty

            # Compute sold_value as sum of pos.order sales
            pos_order_lines = self.env['pos.order.line'].search([('product_id', '=', product.id),
                                                                ('create_date', '>=', self.datefrom), 
                                                                ('create_date', '<=', self.dateto)])
            if len(pos_order_lines) > 0:
                product_sales = [(x.qty, x.qty * x.price_unit) for i, x in enumerate(pos_order_lines)]
            else:
                product_sales = [(0.0,0.0)]
            product_sales = [sum(i) for i in zip(*product_sales)]
            item['sold_iqty'] += product_sales[0]
            item['sold_value'] += product_sales[1]

            # Add sales outside pos (invoiced)
            invoice_lines = self.env['account.invoice.line'].search([
                                        ('product_id', '=', product.id),
                                        ('account_id', '=', 153),
                                        ('create_date', '>=', self.datefrom), 
                                        ('create_date', '<=', self.dateto)])
            if len(invoice_lines) > 0:
                product_sales = [(x.quantity, x.price_subtotal) for i, x in enumerate(invoice_lines)]
            else:
                product_sales = [(0.0,0.0)]
            product_sales = [sum(i) for i in zip(*product_sales)]
            item['sold_iqty'] += product_sales[0]
            item['sold_value'] += product_sales[1]

            # Compute bought value as sum of purchase orders invoice line (including taxes)
            # also track the invoiced qty
            invoice_lines = self.env['account.invoice.line'].search([
                                        ('product_id', '=', product.id),
                                        ('account_id', '=', 128),
                                        ('create_date', '>=', self.datefrom), 
                                        ('create_date', '<=', self.dateto)])

            if len(invoice_lines) > 0:
                product_sales = [(math.copysign(x.quantity, x.price_subtotal_signed), math.copysign(x.quantity, x.price_subtotal_signed) * get_product_cost_at_date(product.id, x.create_date)) 
                                    for i, x in enumerate(invoice_lines)]
            else:
                product_sales = [(0.0,0.0)]

            product_sales = [sum(i) for i in zip(*product_sales)]
            item['bought_iqty'] = product_sales[0] * (template.uom_id.factor/template.uom_po_id.factor)
            item['invoiced_value'] = product_sales[1] * (template.uom_id.factor/template.uom_po_id.factor)
            product_price_start = self.env['product.price.history'].search([('product_id', '=', product.id),('datetime', '<=', self.previous_period.dateto)]
                                    ,limit=1,order='datetime desc').cost or 0.0
            product_price_end = self.env['product.price.history'].search([('product_id', '=', product.id),('datetime', '<=', self.dateto)]
                                    ,limit=1,order='datetime desc').cost or 0.0
            product_price_latest = self.env['product.price.history'].search([('product_id', '=', product.id)]
                                    ,limit=1,order='datetime desc').cost or 0.0
            product_selling_price_latest = self.env['product.customer.price.history'].search([('product_id', '=', product.id)]
                                    ,limit=1,order='datetime desc').price or 0.0
            product_selling_price_period = self.env['product.customer.price.history'].search([('product_id', '=', product.id),('datetime', '<=', self.dateto)]
                                    ,limit=1,order='datetime desc').price or 0.0
            item['startqty'] = self.env['logisfloo.inventory.reportline'].search([
                                        ('inventory_period_id', '=', self.previous_period.id), 
                                        ('product_id', '=', item['product_id'])
                                        ]).invqty
            endqty = item['startqty'] + item['boughtqty'] + item['extraqty'] - item['soldqty'] - item['lossqty']
            item['corrqty'] = item['extraqty']-item['lossqty']
            item['corr_value'] = item['corrqty'] * product_price_end
            item['start_value'] = item['startqty'] * product_price_start
            item['end_value'] = endqty * product_price_end
            item['diffqty'] = round(item['invqty'] - endqty,3)
            item['inv_value'] = item['invqty'] * product_price_end
            item['sold_value_period'] = item['sold_iqty'] * product_selling_price_period
            item['sold_cost_period'] = item['sold_iqty'] * product_price_end
            item['sold_value_latest'] = item['sold_iqty'] * template.list_price
            item['sold_cost_latest'] = item['sold_iqty'] * product_price_latest
            sold_purchase_value =  round((item['start_value']
                                    + item['bought_value'] 
                                    - item['end_value']),2) if item['sold_value'] != 0 else 0.0 
            sold_margin = item['sold_value'] - sold_purchase_value - item['corr_value']                                 
            sold_ref_value = sold_purchase_value + item['corr_value'] 
            margin = round(item['sold_value']/sold_purchase_value * 100 - 100,2) if sold_purchase_value != 0 and item['sold_value'] != 0 else 0.0   
            margin_corr = round(item['sold_value']/sold_ref_value * 100 - 100,2) if sold_ref_value != 0 and item['sold_value'] != 0 else 0.0
            margin_period = round(item['sold_value_period']/item['sold_cost_period'] * 100 - 100,2) if item['sold_cost_period'] != 0 else 0.0
            margin_latest = round(item['sold_value_latest']/item['sold_cost_latest'] * 100 - 100,2) if item['sold_cost_latest'] != 0 else 0.0
            if not self.previous_period:
                # The initial period represent the starting point of the inventory and accounting data:
                # - must only contain data for the end qty and end value
                # - start qty and values are set to the same values as the end values
                # - other values are zeroed as they are rolled up in the end values 
                item['corrqty'] = 0.0
                item['corr_value'] = 0.0
                item['boughtqty'] = 0.0
                item['bought_value'] = 0.0
                item['soldqty'] = 0.0
                item['sold_value'] = 0.0
                item['sold_value_period'] = 0.0
                item['sold_cost_period'] = 0.0
                item['sold_value_latest'] = 0.0
                item['sold_cost_latest'] = 0.0
                item['startqty'] = endqty
                item['start_value'] = item['end_value']

            reportline.create({
                'product_id': item['product_id'],
                'product_template_id': product.product_tmpl_id.id,
                'movecount': item['movecount'],
                'startqty': item['startqty'],
                'endqty': endqty,
                'soldqty': item['soldqty'],
                'boughtqty': item['boughtqty'],
                'lossqty': item['lossqty'],
                'extraqty': item['extraqty'],
                'corrqty': item['corrqty'],
                'unknownqty': item['unknownqty'],
                'inventory_period_id': self.id,
                'start_value': item['start_value'],
                'end_value': item['end_value'],
                'bought_value': item['bought_value'],
                'corr_value': item['corr_value'],
                'invoiced_value': item['invoiced_value'],
                'sold_value': item['sold_value'],
                'sold_value_period': item['sold_value_period'],
                'sold_cost_period': item['sold_cost_period'],
                'sold_value_latest': item['sold_value_latest'],
                'sold_cost_latest': item['sold_cost_latest'],
                'sold_purchase_value': sold_purchase_value,
                'bought_iqty': item['bought_iqty'],
                'sold_iqty': item['sold_iqty'],                
                'margin': margin,
                'margin_corr': margin_corr,
                'margin_period': margin_period,
                'margin_latest': margin_latest,
                'margin_sold': sold_margin,
                'invqty': item['invqty'],
                'diffqty': item['diffqty'],
                'inv_value': item['inv_value'],
                })
        _logger.info('Rebuild inventory report for period %s - done', self.name)
 
class LogisflooInventoryReportLine(models.Model):
    _description = 'Inventory Report Line'
    _name = "logisfloo.inventory.reportline"
    _order = 'product_id asc, inventory_period_id asc'
    _rec_name = "rec_name"

    @api.model
    def _default_currency(self):
        return self.company_id.currency_id or self.env.user.company_id.currency_id

    company_id = fields.Many2one('res.company', string='Company', change_default=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get('logisfloo.inventory.reportline'))

    inventory_period_id = fields.Many2one('logisfloo.inventory.period', string='Period', required=True, track_visibility='onchange')
    rec_name = fields.Char('_rec_name', compute='_get_rec_name', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, track_visibility='onchange')
    product_template_id = fields.Many2one('product.template', string='Product Template', required=True, track_visibility='onchange')
    product_category = fields.Char('Category', compute='_get_product_category', readonly=True, store=True)
    product_supplier = fields.Char('Supplier', compute='_get_product_supplier_name', readonly=True, store=True)
    product_actual_margin = fields.Float('Price margin', digits=(3,2), compute='_get_product_actual_margin', readonly=True)
    product_active = fields.Char('Active', compute='_get_product_active', readonly=True)
    movecount = fields.Float(string='Number of moves for this product',required=True, track_visibility='onchange', default=0.0, help="Number of stock moves during this period") 

    startqty = fields.Float(string='Start Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity at start of this period")
    endqty = fields.Float(string='End Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity at end of this period")
    invqty = fields.Float(string='Inventory Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity at inventory of this period")
    diffqty = fields.Float(string='Inventory-End Qty',required=True, track_visibility='onchange', default=0.0, help="Delta Quantity at inventory and at end of this period")
    soldqty = fields.Float(string='Sold Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity sold during this period")
    boughtqty = fields.Float(string='Purch Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity bought during this period")
    lossqty = fields.Float(string='Lost Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity lost during this period")
    extraqty = fields.Float(string='Extra Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity extra during this period")
    corrqty = fields.Float(string='Corr Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity corrected during this period")
    unknownqty = fields.Float(string='Unassigned Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity unassigned during this period")
    sold_iqty = fields.Float(string='Customer Invoiced Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity sold (as per customer pos orders/invoices) during this period") 
    bought_iqty = fields.Float(string='Vendor Invoiced Qty',required=True, track_visibility='onchange', default=0.0, help="Quantity bought (as per vendor invoices) during this period") 

    currency_id = fields.Many2one('res.currency', string='Currency',
        required=True, readonly=True, states={'draft': [('readonly', False)]},
        default=_default_currency, track_visibility='always') 
    start_value = fields.Monetary(string='Start value', currency_field='currency_id', readonly=True, store=True, help="Starting stock value")
    bought_value = fields.Monetary(string='Purch value', currency_field='currency_id', readonly=True, store=True, help="Quantity bought value")
    invoiced_value = fields.Monetary(string='Invoiced value', currency_field='currency_id', readonly=True, store=True, help="Invoiced value")
    sold_value = fields.Monetary(string='Sold value', currency_field='currency_id', readonly=True, store=True, help="Stock sold value")
    sold_value_period = fields.Monetary(string='Sold value at last period price', currency_field='currency_id', readonly=True, store=True, help="Stock sold value at last period price")
    sold_cost_period = fields.Monetary(string='Cost of sold at last period price', currency_field='currency_id', readonly=True, store=True, help="Stock cost value at last period price")
    sold_value_latest = fields.Monetary(string='Sold value at current price', currency_field='currency_id', readonly=True, store=True, help="Stock sold value at current price")
    sold_cost_latest = fields.Monetary(string='Cost of sold at current price', currency_field='currency_id', readonly=True, store=True, help="Stock cost value at current price")
    corr_value = fields.Monetary(string='Corr value', currency_field='currency_id', readonly=True, store=True, help="Stock correction value")
    sold_purchase_value = fields.Monetary(string='Cost of sold', currency_field='currency_id', readonly=True, store=True, help="Stock sold purchase value")
    end_value = fields.Monetary(string='End value', currency_field='currency_id', readonly=True, store=True, help="Ending stock value")
    inv_value = fields.Monetary(string='Inv value', currency_field='currency_id', readonly=True, store=True, help="Stock inventory value")
    margin = fields.Float(string='Margin %',required=True, track_visibility='onchange', default=0.0, help="Actual margin") 
    margin_corr = fields.Float(string='Margin Corr %',required=True, track_visibility='onchange', default=0.0, help="Margin corrected")
    margin_period = fields.Float(string='Margin Period %',required=True, track_visibility='onchange', default=0.0, help="Margin with price and cost at end of period") 
    margin_latest = fields.Float(string='Margin Latest %',required=True, track_visibility='onchange', default=0.0, help="Margin with current price and cost")
    margin_sold = fields.Float(string='Margin Sold',required=True, track_visibility='onchange', default=0.0, help="Margin with current price and cost")


    price_history_ids = fields.One2many("product.customer.price.history", "product_id", domain=[],compute='get_price_history', help="History of selling price")  
    cost_history_ids = fields.One2many("product.price.history", "product_id", domain=[],compute='get_cost_history', help="History of purchase cost")  

    @api.one
    @api.depends('product_id.product_tmpl_id.seller_ids')
    def _get_product_supplier_name(self):
        if len(self.product_id.product_tmpl_id._get_main_supplier_info()) > 0:
            #vendor = self.env['res.partner'].search([('id','=',self.product_id.product_tmpl_id._get_main_supplier_info()[0].name)])
            self.product_supplier = self.product_id.product_tmpl_id._get_main_supplier_info()[0].name.name
        else:
            self.product_supplier = "Pas de fournisseur défini"

    @api.one
    @api.depends('product_id.product_tmpl_id.seller_ids')
    def _get_rec_name(self):
        self.rec_name = self.product_id.name + " Period: " + self.inventory_period_id.name

    @api.one
    @api.depends('product_id.product_tmpl_id.categ_id')
    def _get_product_category(self):
        self.product_category = self.product_id.product_tmpl_id.categ_id.name

    @api.one
    @api.depends('product_id.product_tmpl_id.actual_margin')
    def _get_product_actual_margin(self):
        self.product_actual_margin = round(self.product_id.product_tmpl_id.actual_margin,2)

    @api.one
    @api.depends('product_id.product_tmpl_id.active')
    def _get_product_active(self):
        self.product_active = self.product_id.product_tmpl_id.active

    # Extend read group to compute the margin on a Group By selection
    def read_group(self, cr, uid, domain, fields, groupby, offset=0, limit=None, context=None, orderby=False, lazy=True):
        res = super(LogisflooInventoryReportLine, self).read_group(cr, uid, domain, fields, groupby, offset, limit=limit, context=context, orderby=orderby, lazy=lazy)
        for line in res:
            resperiods = super(LogisflooInventoryReportLine, self).read_group(cr, uid, line['__domain'], fields, [u'inventory_period_id'], offset, limit=limit, context=context, orderby=orderby, lazy=lazy)            
#            del line['sold_purchase_value']
            line['startqty'] = resperiods[0]['startqty']
            line['endqty'] = resperiods[-1]['endqty']
            line['start_value'] = resperiods[0]['start_value']
            line['end_value'] = resperiods[-1]['end_value']
            sold_ref_value = line['start_value'] + line['bought_value'] - line['end_value']
#            line['margin'] = round((line['sold_value']/sold_ref_value) * 100 - 100,2) if sold_ref_value != 0 and line['sold_value'] != 0 else 0.0
            line['margin_corr'] = round((line['sold_value']/(sold_ref_value + line['corr_value'])) * 100 - 100,2) if sold_ref_value != 0 and line['sold_value'] != 0 else 0.0
            line['margin_period'] = round((line['sold_value_period']/line['sold_cost_period']) * 100 - 100,2) if line['sold_cost_period'] != 0 else 0.0
            line['margin_latest'] = round((line['sold_value_latest']/line['sold_cost_latest']) * 100 - 100,2) if line['sold_cost_latest'] else 0.0
            line['margin_sold'] = round((line['sold_value_latest']/line['sold_cost_latest']) * 100 - 100,2) if line['sold_cost_latest'] else 0.0
            if groupby[0] != u'product_id':
                del line['startqty']
                del line['boughtqty']
                del line['soldqty']
                del line['corrqty']
                del line['endqty']
                del line['invqty']
                del line['diffqty']
        return res

    @api.multi
    def show_customer_price_history(self):
        ctx={}
        return { 
            'res_model': 'product.customer.price.history',
            'src_model': 'logisfloo.inventory.reportline',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain' : [['product_id', '=', self.product_id.id]], 
            'context': ctx,
        }

    @api.multi
    def show_product_cost_history(self):
        ctx={}
        return { 
            'res_model': 'product.price.history',
            'src_model': 'logisfloo.inventory.reportline',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain' : [['product_id', '=', self.product_id.id]], 
            'context': ctx,
        }

    @api.one
    def get_price_history(self):
        price_history = self.env['product.customer.price.history']
        domain=[('product_id', '=',self.product_id.id)]
        self.price_history_ids = price_history.search(domain)

    @api.one
    def get_cost_history(self):
        cost_history = self.env['product.price.history']
        domain=[('product_id', '=',self.product_id.id)]
        self.cost_history_ids = cost_history.search(domain)