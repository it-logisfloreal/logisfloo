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

	@api.one
	@api.depends ('credit')
	def _slate_balance_get(self):
		 self.slate_balance = -self.credit
