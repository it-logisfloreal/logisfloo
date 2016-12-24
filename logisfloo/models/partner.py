# -*- coding: utf-8 -*-
from openerp import models, fields, api, _
from openerp.exceptions import ValidationError
from openerp.addons.beesdoo_base.tools import concat_names

class Partner(models.Model):

    _inherit = 'res.partner'

    ardoise_number = fields.Integer('Ardoise')
    subscription_date = fields.Date('Subscription Date')
    # TODO add subscription_event - pick up from configurable event list, updating subscription date automatically with date of event 
    floreal_logis_membership = fields.Selection([('no', 'No'), ('logis', 'Logis'),('floréal','Floréal')], string="Logis/Floréal")
    add_to_mailing_list = fields.Boolean('Add to Mailing List')                                                                            
