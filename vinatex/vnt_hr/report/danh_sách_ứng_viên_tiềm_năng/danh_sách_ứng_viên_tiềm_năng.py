# file: vinatex/vnt_hr/report/bao_cao_ung_vien_tiem_nang/bao_cao_ung_vien_tiem_nang.py
# -*- coding: utf-8 -*-
import frappe
from frappe import _

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("STT"), "fieldname": "idx", "fieldtype": "Int", "width": 60},
        {"label": _("Họ và tên"), "fieldname": "applicant_name", "fieldtype": "Data", "width": 200},
        {"label": _("Giới tính"), "fieldname": "gender", "fieldtype": "Data", "width": 90},
        {"label": _("Năm sinh"), "fieldname": "date_of_joining", "fieldtype": "Date", "width": 110},
        {"label": _("Trình độ học vấn"), "fieldname": "qualification", "fieldtype": "Data", "width": 160},
        {"label": _("Chuyên môn/Ngành học"), "fieldname": "custom_maj_opt_subj", "fieldtype": "Data", "width": 180},
        {"label": _("Số năm kinh nghiệm"), "fieldname": "custom_years_of_experience", "fieldtype": "Int", "width": 80},
        {"label": _("Chiến dịch tuyển dụng"), "fieldname": "job_title", "fieldtype": "Link", "options": "Job Opening", "width": 150},
        {"label": _("Vị trí ứng tuyển"), "fieldname": "job_opening", "fieldtype": "Data", "width": 250},
        {"label": _("Phòng ban"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 160},
        {"label": _("SĐT"), "fieldname": "phone", "fieldtype": "Data", "width": 130},
        {"label": _("Email"), "fieldname": "email_id", "fieldtype": "Data", "width": 200},
        {"label": _("Ngày nhận hồ sơ"), "fieldname": "custom_date", "fieldtype": "Date", "width": 130},
        {"label": _("Nguồn ứng viên"), "fieldname": "source", "fieldtype": "Data", "width": 140},
        {"label": _("Mức độ tiềm năng"), "fieldname": "applicant_rating", "fieldtype": "Int", "width": 140},
        {"label": _("Trạng thái hiện tại"), "fieldname": "status", "fieldtype": "Data", "width": 150},
        {"label": _("Đề xuất hành động tiếp theo"), "fieldname": "custom_suggested_next_step", "fieldtype": "Data", "width": 220},
    ]

def get_filters():
    """Khai báo filters (tham khảo để viết file .js)."""
    return [
        {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
        {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
        {"fieldname": "department", "label": "Department", "fieldtype": "Link", "options": "Department"},
        {"fieldname": "job_opening", "label": "Job Opening", "fieldtype": "Link", "options": "Job Opening"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select",
         "options": "\nOpen\nRejected\nAccepted\nHold\nPending\nScheduled\nOffered\nJoined"},
        {"fieldname": "potential_level", "label": "Potential Level", "fieldtype": "Data"},
    ]

def get_data(filters):
    conds = []
    params = {}

    # ứng ngày nhận hồ sơ: ưu tiên application_date, fallback creation
    app_date_expr = "COALESCE(ja.custom_date, DATE(ja.creation))"

    if filters.get("from_date"):
        conds.append(f"{app_date_expr} >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conds.append(f"{app_date_expr} <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    if filters.get("department"):
        conds.append("jo.department = %(department)s")
        params["department"] = filters["department"]

    if filters.get("job_opening"):
        conds.append("ja.job_title = %(job_opening)s")
        params["job_opening"] = filters["job_opening"]

    if filters.get("status"):
        conds.append("ja.status = %(status)s")
        params["status"] = filters["status"]

    # if filters.get("potential_level"):
    #     conds.append("ja.custom_potential_level = %(potential_level)s")
    #     params["potential_level"] = filters["potential_level"]

    where_clause = ("WHERE " + " AND ".join(conds)) if conds else ""

    # ⚠️ Nếu hệ bạn dùng field khác:
    # - campaign -> đổi thành custom_recruitment_campaign
    # - years_of_experience -> nếu không có, để 0 hoặc tự tính
    # - proposed_next_action, custom_potential_level: đổi tên nếu khác
    sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY {app_date_expr}, ja.applicant_name) AS idx,
            ja.applicant_name,
			ja.custom_gender as gender,
			ja.custom_date_of_joining as date_of_joining,
			ja.custom_qualification as qualification,
			ja.custom_maj_opt_subj as custom_maj_opt_subj,
			ja.custom_years_of_experience as custom_years_of_experience,
			ja.phone_number as phone,
			ja.custom_date as custom_date,
			ja.source as source,
			ja.custom_suggested_next_step as custom_suggested_next_step,
			ja.status as status,
			ROUND((COALESCE(ja.applicant_rating, 0) / 10.0) * 100, 0) AS applicant_rating,
			ja.email_id as email_id,
			jo.name as job_title,
			jo.job_title as job_opening,
			jo.department as department
        FROM `tabJob Applicant` ja
        LEFT JOIN `tabJob Opening` jo ON jo.name = ja.job_title
        {where_clause}
        ORDER BY {app_date_expr} ASC, ja.applicant_name ASC
    """
    return frappe.db.sql(sql, params, as_dict=True)
