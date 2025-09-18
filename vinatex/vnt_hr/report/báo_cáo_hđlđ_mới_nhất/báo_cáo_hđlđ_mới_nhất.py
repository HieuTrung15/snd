import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": "Mã nhân viên", "fieldname": "employee_code", "fieldtype": "Data", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": "Bộ phận", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 120},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 120},
        {"label": "Vị trí công việc", "fieldname": "job_title", "fieldtype": "Data", "width": 150},
        {"label": "Loại hợp đồng", "fieldname": "type", "fieldtype": "Data", "width": 120},
        {"label": "Lý do ký lại HĐ", "fieldname": "sign_reason", "fieldtype": "Data", "width": 150},
        {"label": "Ngày bắt đầu", "fieldname": "from_date", "fieldtype": "Date", "width": 100},
        {"label": "Ngày kết thúc", "fieldname": "to_date", "fieldtype": "Date", "width": 100},
        {"label": "Ngày ký", "fieldname": "contract_date", "fieldtype": "Date", "width": 100},
        {"label": "Người ký", "fieldname": "signer", "fieldtype": "Data", "width": 120},
        {"label": "Vị trí công việc người ký", "fieldname": "designation_of_signer", "fieldtype": "Data", "width": 150},
        {"label": "Trạng thái", "fieldname": "sign_status", "fieldtype": "Data", "width": 100},
        {"label": "Số quyết định lương cơ bản", "fieldname": "salary_decision_num", "fieldtype": "Data", "width": 150},
        {"label": "Đối tượng lương", "fieldname": "salary_beneficiary", "fieldtype": "Data", "width": 120},
        {"label": "Ngày hiệu lực", "fieldname": "effective_date", "fieldtype": "Date", "width": 100},
        {"label": "Tên thang bảng lương", "fieldname": "salary_scale_name", "fieldtype": "Data", "width": 150},
        {"label": "Ngạch lương", "fieldname": "salary_grade", "fieldtype": "Data", "width": 120},
        {"label": "Bậc lương", "fieldname": "salary_step", "fieldtype": "Data", "width": 120},
        {"label": "Hệ số", "fieldname": "salary_coefficient", "fieldtype": "Float", "width": 100},
        {"label": "Lương cơ bản", "fieldname": "basic_salary", "fieldtype": "Currency", "width": 120},
        {"label": "Phụ cấp kiêm nhiệm", "fieldname": "concurrent_allowance", "fieldtype": "Currency", "width": 150},
    ]

    conditions = []
    values = {}

    if filters.get("employee"):
        conditions.append("emp.name = %(employee)s")
        values["employee"] = filters.get("employee")

    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        values["department"] = filters.get("department")

    if filters.get("from_date"):
        conditions.append("vc.contract_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions.append("vc.contract_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")

    condition_sql = " AND ".join(conditions)
    if condition_sql:
        condition_sql = "WHERE " + condition_sql

    data = frappe.db.sql(f"""
        SELECT *
		FROM (
			SELECT
				emp.name AS employee_code,
				emp.employee_name AS employee_name,
				emp.department AS department,
				emp.designation AS designation,
				vc.job_title AS job_title,
				vc.type AS type,
				vc.sign_reason AS sign_reason,
				vc.from_date AS from_date,
				vc.to_date AS to_date,
				vc.contract_date AS contract_date,
				vc.signer AS signer,
				vc.designation_of_signer AS designation_of_signer,
				vc.sign_status AS sign_status,
				vc.salary_decision_num AS salary_decision_num,
				vc.salary_beneficiary AS salary_beneficiary,
				vc.effective_date AS effective_date,
				vc.salary_scale_name AS salary_scale_name,
				vc.salary_grade AS salary_grade,
				vc.salary_step AS salary_step,
				vc.salary_coefficient AS salary_coefficient,
				vc.basic_salary AS basic_salary,
				vc.concurrent_allowance AS concurrent_allowance,
				ROW_NUMBER() OVER (PARTITION BY emp.name ORDER BY vc.contract_date DESC) AS rn
			FROM
				`tabEmployee` emp
			JOIN
				`tabVNT Contract` vc ON vc.parent = emp.name
			{condition_sql}
		) t
		WHERE rn = 1;
    """, values, as_dict=True)

    return columns, data
