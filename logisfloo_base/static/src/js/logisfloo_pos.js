odoo.define('logisfloo_pos.pos_extension', function (require) {
	"use strict";
    var models = require('point_of_sale.models');
    
 // load extra data from 'res.partner' (slate_number)
	models.load_fields('res.partner','slate_number');

    var db = require('point_of_sale.DB');

    db = db.include({
 	    _partner_search_string: function(partner){
	        var str =  partner.slate_number;
	        if(partner.name){
	            str += '|' + partner.name;
	        }
	        str = '' + partner.id + ':' + str.replace(':','') + '\n';
	        return str;
	    },
    })

});