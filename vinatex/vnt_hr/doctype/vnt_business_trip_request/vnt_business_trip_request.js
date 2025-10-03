frappe.ui.form.on('VNT Business Trip Request', {
  onload: async function (frm) {
    // 1) Tự động lấy Employee theo user hiện tại (nếu chưa có)
    if (!frm.doc.employee) {
      const empRes = await frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name");
      const empName = empRes?.message?.name;
      if (empName) {
        await frm.set_value("employee", empName);
      }
    }

    // 2) Lấy approver theo leave_approvers của Phòng ban
    await set_approver_from_department(frm);
  }
});

// Set approver theo phòng ban của employee
async function set_approver_from_department(frm) {
  try {
    // Nếu đã có approver rồi thì thôi
    if (frm.doc.approver) return;

    const employee = frm.doc.employee;
    if (!employee) return;

    // Lấy phòng ban của nhân viên
    const deptRes = await frappe.db.get_value("Employee", employee, "department");
    const department = deptRes?.message?.department;
    if (!department) return;
    
    // Lấy approver đầu tiên trong bảng con leave_approvers của Department
    // Child doctype mặc định là "Department Approver"
    const approverRows = await frappe.db.get_list("Department Approver", {
      filters: {
        parent: department,
        parenttype: "Department",
        parentfield: "leave_approvers"
      },
      fields: ["approver", "idx"],
      order_by: "idx asc",
      limit: 1
    });

    const approver = approverRows?.[0]?.approver;
    if (approver) {
      await frm.set_value("approver", approver);
    }
  } catch (e) {
    console.error( e);
  }
}
