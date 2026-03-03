const HR_SALARY_USERS = new Set([
  "tult@vinatex.com.vn",
  "thudtx@vinatex.com.vn",
  "thaottt@vinatex.com.vn",
]);

function canManage13thMonthSalary() {
  const user = frappe.session?.user;
  if (!user || user === "Guest") return false;
  if (user === "Administrator") return true;
  return HR_SALARY_USERS.has(user);
}

frappe.listview_settings["VNT 13th Month Salary"] = {
  onload(listview) {
    if (canManage13thMonthSalary()) return;

    listview.page.clear_primary_action();
    listview.page.btn_primary && listview.page.btn_primary.addClass("disabled").addClass("hidden");
  },
};
