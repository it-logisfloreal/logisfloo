odoo.define('logisfloo_base.myform_widgets', function (require) {
"use strict";

	var core = require('web.core');
	var _t = core._t;
	var FieldBooleanButton = core.form_widget_registry.get('boolean_button');
	
	FieldBooleanButton.include({
	    init: function() {
	        className: 'o_stat_info',
	        this._super.apply(this, arguments);
	        switch (this.options["terminology"]) {
		        case "send":
		            this.string_true = _t("Sent");
		            this.hover_true = _t("Sent");
		            this.string_false = _t("To do");
		            this.hover_false = _t("Send");
		            break;
	        }
	    },
	});
});
