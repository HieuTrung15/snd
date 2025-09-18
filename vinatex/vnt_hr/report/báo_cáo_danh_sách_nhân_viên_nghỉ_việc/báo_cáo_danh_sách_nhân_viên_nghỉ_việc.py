import frappe
from frappe.utils.data import today, getdate

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": "Mã nhân viên", "fieldname": "employee_code", "fieldtype": "Data", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "width": 120},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "width": 120},
        {"label": "Vị trí công việc", "fieldname": "job_title", "fieldtype": "Data", "width": 150},
        {"label": "Ngày vào tập đoàn", "fieldname": "date_of_joining", "fieldtype": "Date", "width": 120},
        {"label": "Thâm niên", "fieldname": "seniority", "fieldtype": "Data", "width": 100},

        {"label": "Loại HĐLĐ mới nhất", "fieldname": "contract_type", "fieldtype": "Data", "width": 150},
        {"label": "Ngày hiệu lực hợp đồng", "fieldname": "contract_from_date", "fieldtype": "Date", "width": 120},
        {"label": "Ngày hết hiệu lực hợp đồng", "fieldname": "contract_to_date", "fieldtype": "Date", "width": 120},

        {"label": "Ngày làm việc cuối cùng NV đề xuất", "fieldname": "last_working_date_proposed", "fieldtype": "Date", "width": 150},
        {"label": "Ngày làm việc cuối NS xác nhận", "fieldname": "last_working_date_confirmed", "fieldtype": "Date", "width": 150},

        {"label": "Lý do nghỉ việc", "fieldname": "resignation_reason", "fieldtype": "Data", "width": 200},
        {"label": "Danh sách đen", "fieldname": "blacklist", "fieldtype": "Check", "width": 100},
        {"label": "Lý do chi tiết", "fieldname": "resignation_detail", "fieldtype": "Data", "width": 200},

        # Quyết định liên quan TĐ
        {"label": "Số quyết định", "fieldname": "decision_no", "fieldtype": "Data", "width": 150},
        {"label": "Ngày hiệu lực", "fieldname": "decision_effective_date", "fieldtype": "Date", "width": 120},
        {"label": "Trạng thái", "fieldname": "decision_status", "fieldtype": "Data", "width": 120},
        {"label": "Người ký", "fieldname": "decision_signer", "fieldtype": "Data", "width": 150},
        {"label": "Vị trí người ký", "fieldname": "decision_signer_designation", "fieldtype": "Data", "width": 150},
        {"label": "Ngày ký", "fieldname": "decision_sign_date", "fieldtype": "Date", "width": 120},
        
		 # Quyết định liên quan kết thúc HĐLĐ
        {"label": "Số quyết định", "fieldname": "decision_no_end", "fieldtype": "Data", "width": 150},
        {"label": "Ngày hiệu lực", "fieldname": "decision_effective_date_end", "fieldtype": "Date", "width": 120},
        {"label": "Trạng thái", "fieldname": "decision_status_end", "fieldtype": "Data", "width": 120},
        {"label": "Người ký", "fieldname": "decision_signer_end", "fieldtype": "Data", "width": 150},
        {"label": "Vị trí người ký", "fieldname": "decision_signer_designation_end", "fieldtype": "Data", "width": 150},
        {"label": "Ngày ký", "fieldname": "decision_sign_date_end", "fieldtype": "Date", "width": 120},

        # Placeholder cho các cột tính toán
        {"label": "Tiền trợ cấp thôi việc", "fieldname": "severance_pay", "fieldtype": "Currency", "width": 150},
        {"label": "Tiền trợ cấp mất việc", "fieldname": "job_loss_allowance", "fieldtype": "Currency", "width": 150},
        {"label": "Tiền phép còn lại", "fieldname": "unused_leave_payment", "fieldtype": "Currency", "width": 150},
    ]

def get_data(filters):
    conditions = []
    if filters.get("department"):
        conditions.append(f"emp.department = '{filters.get('department')}'")
    if filters.get("employee"):
        conditions.append(f"emp.name = '{filters.get('employee')}'")
    if filters.get("from_date"):
        conditions.append(f"vc.designation_of_signer  >= '{filters.get('from_date')}'")
    if filters.get("to_date"):
        conditions.append(f"vc.designation_of_signer  <= '{filters.get('to_date')}'")
    if filters.get("company"):
        conditions.append(f"emp.company = '{filters.get('company')}'")
    
    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = " AND " + where_clause

    sql = f"""
        SELECT
            emp.name AS employee_code,
            emp.employee_name,
            emp.department,
            emp.designation,
            vc.job_title,
            emp.date_of_joining,
            CONCAT(FLOOR(DATEDIFF(CURDATE(), emp.date_of_joining)/365), ' năm') AS seniority,
            vc.type AS contract_type,
            vc.from_date AS contract_from_date,
            vc.to_date AS contract_to_date,
            vc.salary_decision_num AS decision_no,
            vc.effective_date AS decision_effective_date,
            vc.sign_status AS decision_status,
            vc.signer AS decision_signer,
            vc.designation_of_signer AS decision_signer_designation,
            vc.contract_date AS decision_sign_date
        FROM
            `tabEmployee` emp
        
        LEFT JOIN `tabVNT Contract` vc 
            ON vc.parent = emp.name
            AND vc.contract_date = (
                SELECT MAX(vc2.contract_date)
                FROM `tabVNT Contract` vc2
                WHERE vc2.parent = emp.name
            )
        WHERE emp.status = 'Left' {where_clause}
    """

    data = frappe.db.sql(sql, as_dict=True)

    # Thêm placeholder
    for d in data:
        d["severance_pay"] = ""
        d["job_loss_allowance"] = ""
        d["unused_leave_payment"] = ""

    return data
