// Hide the workflow "Help" item in Actions dropdown on Form views.
(() => {
	const patch_form_workflow_help = () => {
		const states = frappe?.ui?.form?.States;
		if (!states?.prototype) {
			// Retry after core form assets are loaded.
			setTimeout(patch_form_workflow_help, 200);
			return;
		}

		const proto = states.prototype;
		if (proto._vnt_hide_workflow_help_patched) {
			return;
		}
		proto._vnt_hide_workflow_help_patched = true;

		// Frappe adds this item from setup_help(); keep it empty to disable.
		proto.setup_help = function () {};
	};

	if (window?.frappe) {
		patch_form_workflow_help();
	} else {
		$(document).ready(patch_form_workflow_help);
	}
})();
