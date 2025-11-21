frappe.ui.form.on('Form', {
    onload() {
        $('body').addClass('full-width');
    }
});

$(document).on('app_ready', function () {
    $('body').addClass('full-width');
});
