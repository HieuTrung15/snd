# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import io
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, escape_html, flt, get_first_day, get_last_day, getdate, now_datetime
from openpyxl.cell.cell import MergedCell
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HR_SALARY_USERS = {
    "tult@vinatex.com.vn",
    "hoaltm@vinatex.com.vn",
    "thaottt@vinatex.com.vn",
}


class VNTMonthlyPayroll(Document):
    def before_insert(self):
        self._enforce_creator_whitelist()

    def validate(self):
        self._ensure_no_submitted_duplicate()
        self._enforce_da_chuyen_luong_lock()

    def before_cancel(self):
        if cint(self.da_chuyen_luong):
            frappe.throw(_("Không thể hủy bảng lương sau khi đã chuyển"))

    def on_submit(self):
        self.create_salary_slips()

    def on_cancel(self):
        self.delete_salary_slips()

    def create_salary_slips(self):
        if not (self.month and self.year):
            frappe.throw(_("Vui lòng chọn Tháng và Năm trước khi submit bảng lương."))

        if not self.items:
            return

        for item in self.items:
            employee = (item.employee or "").strip()
            if not employee:
                continue

            self._cancel_existing_salary_slips(employee)
            slip_doc = frappe.new_doc("VNT Salary Slip")
            slip_doc.flags.ignore_permissions = True
            slip_doc.employee = employee
            slip_doc.employee_name = item.employee_name or None
            slip_doc.month = self.month
            slip_doc.year = self.year
            slip_fields = self._build_salary_slip_fields(item)
            for fieldname, value in slip_fields.items():
                slip_doc.set(fieldname, value)
            # rendered_html = self._render_salary_slip_html(item)
            # slip_doc.rendered_html = rendered_html
            # slip_doc.html = rendered_html

            slip_doc.set_new_name(self._build_salary_slip_name(employee))
            slip_doc.insert(ignore_permissions=True)
            slip_doc.submit()

    def delete_salary_slips(self):
        if not (self.month and self.year):
            return

        employee_codes = [row.employee for row in (self.items or []) if row.employee]
        if not employee_codes:
            return

        slips = frappe.get_all(
            "VNT Salary Slip",
            filters={
                "month": self.month,
                "year": self.year,
                "employee": ("in", employee_codes),
                "docstatus": ("!=", 2),
            },
            fields=["name"],
        )

        for slip in slips:
            slip_doc = frappe.get_doc("VNT Salary Slip", slip.name)
            slip_doc.flags.ignore_permissions = True
            if slip_doc.docstatus == 1:
                slip_doc.cancel()
            # slip_doc.delete(ignore_permissions=True)

    def _cancel_existing_salary_slips(self, employee):
        if not (self.month and self.year):
            return

        existing_slips = frappe.get_all(
            "VNT Salary Slip",
            filters={
                "employee": employee,
                "month": self.month,
                "year": self.year,
                "docstatus": ("in", [0, 1]),
            },
            fields=["name", "docstatus"],
        )

        for slip in existing_slips:
            slip_doc = frappe.get_doc("VNT Salary Slip", slip.name)
            slip_doc.flags.ignore_permissions = True
            if slip_doc.docstatus == 1:
                slip_doc.cancel()
            # else:
            #     slip_doc.delete(ignore_permissions=True)

    def _build_salary_slip_name(self, employee):
        month = (self.month or "").zfill(2)
        year = str(self.year or "")
        suffix = now_datetime().strftime("%Y%m%d%H%M%S")
        unique_part = frappe.generate_hash(length=4)
        return f"{employee}-{year}{month}-{suffix}{unique_part}"

    def _enforce_da_chuyen_luong_lock(self):
        """Chỉ Administrator mới được bỏ tick Đã chuyển lương."""
        if self.is_new():
            return

        previous_flag = frappe.db.get_value(self.doctype, self.name, "da_chuyen_luong")
        if cint(previous_flag) and not cint(self.da_chuyen_luong) and frappe.session.user != "Administrator":
            # Giữ lại trạng thái đã chuyển, không cho phép bỏ tick
            self.da_chuyen_luong = previous_flag
            frappe.throw(_("Không thể bỏ tick khi \"Đã chuyển lương\". Vui lòng liên hệ Ban CNTT & CĐS."))

    def _enforce_creator_whitelist(self):
        """Chỉ cho phép HR lương/Administrator tạo mới bảng lương."""
        if not self.is_new():
            return

        current_user = frappe.session.user
        if current_user == "Administrator":
            return

        if current_user not in HR_SALARY_USERS:
            frappe.throw(_("Bạn không được phép tạo bảng lương tháng. Vui lòng liên hệ HR."))

    def before_update_after_submit(self):
        self._enforce_da_chuyen_luong_lock()

    def _build_salary_slip_fields(self, item):
        standard_days = flt(self.standard_working_days) or 0
        luong_cb = flt(item.luong_cb)
        so_phep = flt(item.sophep)
        so_vr = flt(item.so_ngay_nghi_vr)
        daily_salary = (luong_cb / standard_days) if standard_days else 0
        luong_nghi_phep = daily_salary * so_phep
        luong_nghi_vr = daily_salary * so_vr

        return {
            "so_ngay_cong": flt(item.ngay_cong),
            "so_ngay_nghi_tinh_phep": so_phep,
            "so_ngay_nghi_viec_rieng_co_huong_luong": so_vr,
            "so_ngay_nghi_khong_luong": flt(item.nghi_kluong_bhxh),
            "he_so_luong_co_ban": flt(item.hs_luong_cb),
            "hs_pc_dang": flt(item.hs_pc_dang_1),
            "hs_pc_kiem_nhiem": flt(item.hs_pc_kiem_nhiem1),
            "luong_co_ban": luong_cb,
            "pc_dang": flt(item.pc_dang1),
            "pc_kiem_nhiem": flt(item.pc_kiem_nhiem1),
            "so_nguoi_phu_thuoc": flt(item.so_npt),
            "he_so_luong_cbcv": flt(item.he_so_cbnv),
            "luong_cbcv": flt(item.tien_luong_hqcv),
            "pc_dang2": flt(item.pc_dang2),
            "pc_kiem_nhiem2": flt(item.pc_kiem_nhiem2),
            "luong_ngay_phep": luong_nghi_phep,
            "luong_ngay_nghi_co_huong_luong": luong_nghi_vr,
            "cong_tac_phi": flt(item.tien_khoan_ct),
            "truy_linh": flt(item.truylinh),
            "tien_an_ca": flt(item.tien_an),
            "tong_thu_nhap": flt(item.tong_thu_nhap),
            "xh_yt_tn": flt(item.xh_yt_tn),
            "cong_doan": flt(item.doan_phi_cd),
            "thue_tncn": flt(item.tncn_tam_thu),
            "thue_tncn_nam_truoc": flt(item.truy_thu) - flt(item.duoc_hoan_lai),
            "thuc_linh": flt(item.thuc_linh),
        }

    def _ensure_no_submitted_duplicate(self):
        """Ngăn tạo trùng bảng lương đã xác nhận cùng kỳ."""
        if not (self.month and self.year and self.branch):
            return

        month = str(self.month).zfill(2)
        year_val = cint(self.year)
        branch = self.branch
        filters = {
            "month": month,
            "year": year_val,
            "branch": branch,
            "docstatus": 1,
        }
        if self.name:
            filters["name"] = ("!=", self.name)

        existing = frappe.get_all(
            "VNT Monthly Payroll",
            filters=filters,
            pluck="name",
            limit_page_length=1,
        )
        if existing:
            frappe.throw(
                _("Đã tồn tại bảng lương đã xác nhận cho tháng {0}/{1} chi nhánh {2}. Không thể lưu mới!").format(
                    month, year_val, branch
                )
            )

    def _render_salary_slip_html(self, item):
        standard_days = flt(self.standard_working_days) or 0
        luong_cb = flt(item.luong_cb)
        so_phep = flt(item.sophep)
        so_vr = flt(item.so_ngay_nghi_vr)
        daily_salary = luong_cb / standard_days if standard_days else 0
        luong_nghi_phep = daily_salary * so_phep
        luong_nghi_vr = daily_salary * so_vr

        def fmt_number(value, decimals=0, blank_for_zero=False):
            if value is None:
                return ""
            number = flt(value, decimals)
            if blank_for_zero and abs(number) < 0.0001:
                return ""
            if decimals:
                formatted = f"{number:,.{decimals}f}".rstrip("0").rstrip(".")
            else:
                formatted = f"{int(round(number)):,}"
            return formatted

        def fmt_currency(value, blank_for_zero=True):
            if value is None:
                return ""
            amount = flt(value, 2)
            if blank_for_zero and abs(amount) < 0.0001:
                return ""
            formatted = f"{amount:,.0f}"
            if formatted == "0" and blank_for_zero:
                return ""
            return formatted

        def section_row(title):
            return f'<tr class="section-row"><td colspan="4">{escape_html(title)}</td></tr>'

        def value_row(idx, label, value, indent=False):
            label_html = escape_html(label)
            value_html = escape_html(value) if value else ""
            index_html = escape_html(idx) if idx else ""
            indent_class = " indent" if indent else ""
            return (
                f'<tr>'
                f'<td class="index">{index_html}</td>'
                f'<td class="label{indent_class}">{label_html}</td>'
                f'<td class="colon">:</td>'
                f'<td class="value">{value_html}</td>'
                f'</tr>'
            )

        rows = [
            section_row("I. THÔNG TIN CHUNG"),
            value_row("1", "Số ngày công", fmt_number(item.ngay_cong, 1)),
            value_row("2", "Số ngày nghỉ tính phép", fmt_number(item.sophep, 0)),
            value_row("3", "Số ngày nghỉ việc riêng có hưởng lương", fmt_number(item.so_ngay_nghi_vr, 0)),
            value_row(
                "4",
                "Số ngày nghỉ không lương/ Nghỉ ốm/ TS nam",
                fmt_number(item.nghi_kluong_bhxh, 0, blank_for_zero=True),
            ),
            value_row("5", "Hệ số lương cơ bản", fmt_number(item.hs_luong_cb, 2, blank_for_zero=True)),
            value_row("6", "Hệ số phụ cấp", ""),
            value_row("", "a. Trách nhiệm Đảng", fmt_number(item.hs_pc_dang_1, 2, blank_for_zero=True), indent=True),
            value_row(
                "",
                "b. Kiêm nhiệm Đoàn thể",
                fmt_number(item.hs_pc_kiem_nhiem1, 2, blank_for_zero=True),
                indent=True,
            ),
            value_row("7", "Tiền lương tính BHXH", ""),
            value_row("", "a. Lương cơ bản", fmt_currency(item.luong_cb), indent=True),
            value_row("", "b. PC trách nhiệm Đảng", fmt_currency(item.pc_dang1), indent=True),
            value_row("", "c. PC kiêm nhiệm Đoàn thể", fmt_currency(item.pc_kiem_nhiem1), indent=True),
            value_row("8", "Số người phụ thuộc", fmt_number(item.so_npt, 0, blank_for_zero=True)),

            section_row("II. TỔNG THU NHẬP"),
            value_row("1", "Hệ số lương CBCV", fmt_number(item.he_so_cbnv, 2, blank_for_zero=True)),
            value_row("2", "Lương CBCV", fmt_currency(item.tien_luong_hqcv)),
            value_row("3", "Phụ cấp", ""),
            value_row("", "a. Trách nhiệm Đảng", fmt_currency(item.pc_dang2), indent=True),
            value_row("", "b. Kiêm nhiệm Đoàn thể", fmt_currency(item.pc_kiem_nhiem2), indent=True),
            value_row("4", "Thù lao (HĐQT, Ban KS)", fmt_currency(item.get("thu_lao_hdqt"))),
            value_row("5", "Tiền lương CQĐH, KTT", fmt_currency(item.tien_luong_hqcv_cu)),
            value_row("6", "Lương ngày phép", fmt_currency(luong_nghi_phep)),
            value_row("7", "Lương ngày nghỉ VR có hưởng lương", fmt_currency(luong_nghi_vr)),
            value_row("8", "Truy lĩnh", fmt_currency(item.truylinh, blank_for_zero=False)),
            value_row("9", "Tiền ăn ca", fmt_currency(item.tien_an)),
            value_row("10", "Khoản công tác phí", fmt_currency(item.tien_khoan_ct)),
            value_row("", "Tổng thu nhập", fmt_currency(item.tong_thu_nhap, blank_for_zero=False), indent=True),

            section_row("III. CÁC KHOẢN TRỪ VÀO LƯƠNG"),
            value_row("1", "BHXH, BHYT, BHTN (10,5%)", fmt_currency(item.xh_yt_tn, blank_for_zero=False)),
            value_row("2", "Công đoàn phí (1%)", fmt_currency(item.doan_phi_cd, blank_for_zero=False)),
            value_row("3", "Thuế TNCN tạm thu", fmt_currency(item.tncn_tam_thu, blank_for_zero=False)),
            value_row(
                "4",
                "Thuế TNCN năm 2024",
                fmt_currency(flt(item.truy_thu) - flt(item.duoc_hoan_lai), blank_for_zero=True),
            ),
        ]

        if flt(item.khac):
            rows.append(value_row("5", "Các khoản khác", fmt_currency(item.khac, blank_for_zero=False)))

        rows.extend(
            [
                section_row("IV. THỰC LĨNH (II - III)"),
                value_row("", "Thực lĩnh", fmt_currency(item.thuc_linh, blank_for_zero=False)),
            ]
        )

        header = (
            f'<div class="salary-slip-header">'
            f'<div><strong>Nhân sự:</strong> {escape_html(item.employee_name or "")} ({escape_html(item.employee or "")})</div>'
            f'<div><strong>Kỳ lương:</strong> Tháng {escape_html(self.month or "")} / {escape_html(str(self.year or ""))}</div>'
            f'<div><strong>Bảng lương:</strong> {escape_html(self.name)}</div>'
            f'</div>'
        )

        style = (
            "<style>"
            ".salary-slip-wrapper{font-size:12px;font-family:var(--font-family,'Inter','Helvetica','Arial',sans-serif);}"  # noqa: E501
            ".salary-slip-header{margin-bottom:8px;}"
            ".salary-slip-header div{margin-bottom:2px;}"
            ".salary-slip-table{width:100%;border-collapse:collapse;}"
            ".salary-slip-table td{border:1px solid #444;padding:4px 6px;vertical-align:top;}"
            ".salary-slip-table .section-row td{background:#f4f4f4;font-weight:600;text-transform:uppercase;text-align:left;}"
            ".salary-slip-table .index{width:42px;text-align:center;font-weight:600;}"
            ".salary-slip-table .label{width:55%;}"
            ".salary-slip-table .label.indent{padding-left:18px;}"
            ".salary-slip-table .colon{width:18px;text-align:center;font-weight:600;}"
            ".salary-slip-table .value{width:25%;text-align:right;font-weight:600;}"
            "</style>"
        )

        table_html = "".join(rows)
        return f'<div class="salary-slip-wrapper">{style}{header}<table class="salary-slip-table">{table_html}</table></div>'


@frappe.whitelist()
def get_active_employees(company=None, branch=None):
    """Return active employees filtered by company and branch (if provided)."""
    filters = {"status": "Active"}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch

    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name",
            "employee_name",
            "designation",
            "company",
            "branch",
            "employment_type",
            "custom_party_member",
            "custom_relation_number",
        ],
        order_by="employee_name asc",
    )


@frappe.whitelist()
def has_submitted_payroll(month=None, year=None, branch = None):
    """Kiểm tra đã có bảng lương trạng thái Đã xác nhận cho kỳ chỉ định hay chưa."""
    if not (month and year):
        return False

    month_str = str(month).zfill(2)
    year_val = cint(year)
    branch = branch
    exists = frappe.get_all(
        "VNT Monthly Payroll",
        filters={
            "month": month_str,
            "year": year_val,
            "docstatus": 1,
            "branch": branch
        },
        pluck="name",
        limit_page_length=1,
    )
    return bool(exists)


@frappe.whitelist()
def salary_slip_exists(month=None, year=None, branch=None):
    """Kiểm tra đã có phiếu lương (chưa cancel) cho chi nhánh trong kỳ hay chưa."""
    if not (month and year and branch):
        return False

    month_str = str(month).zfill(2)
    year_val = cint(year)
    branch_val = (branch or "").strip()
    if not branch_val:
        return False

    sql = """
        SELECT 1
        FROM `tabVNT Salary Slip` AS slip
        INNER JOIN `tabEmployee` AS emp ON emp.name = slip.employee
        WHERE slip.month = %(month)s
          AND slip.year = %(year)s
          AND slip.docstatus != 2
          AND emp.branch = %(branch)s
        LIMIT 1
    """
    return bool(frappe.db.sql(sql, {"month": month_str, "year": year_val, "branch": branch_val}))


@frappe.whitelist()
def check_existing_payroll(month=None, year=None, branch=None):
    """Trả về trạng thái có bảng lương đã xác nhận hoặc phiếu lương đã tạo cho kỳ và chi nhánh."""
    submitted_payroll = has_submitted_payroll(month=month, year=year, branch=branch)
    existing_salary_slip = salary_slip_exists(month=month, year=year, branch=branch)
    return {
        "submitted_payroll": bool(submitted_payroll),
        "salary_slip": bool(existing_salary_slip),
    }


def get_employee_contracts(employee, period_start, period_end):
    """Return employment contracts overlapping the requested payroll period."""
    if not employee or not period_start or not period_end:
        return []

    sql = """
        SELECT
            name,
            type,
            contract_no,
            contract_date,
            from_date,
            to_date,
            contract_term,
            validity
        FROM `tabVNT Contract`
        WHERE parent = %(employee)s
          AND parenttype = 'Employee'
          AND parentfield = 'custom_vnt_contract'
          AND from_date IS NOT NULL
          AND from_date <= %(period_end)s
          AND (to_date IS NULL OR to_date >= %(period_start)s)
        ORDER BY from_date, name
    """
    params = {
        "employee": employee,
        "period_start": period_start,
        "period_end": period_end,
    }
    return frappe.db.sql(sql, params, as_dict=True)


def get_employee_salary_history(employee):
    """Return salary history entries for the employee."""
    if not employee:
        return []

    return frappe.get_all(
        "VNT Employee Salary History",
        filters={
            "parent": employee,
            "parenttype": "Employee",
            "parentfield": "custom_emp_salary_history",
        },
        fields=[
            "name",
            "he_so",
            "from_date",
            "to_date",
            "muc_luong",
            "thue_tncn_trich_them",
            "tien_gui_xe",
            "khong_an_ca",
            "khong_ctp",
            "thue_tam_trich",
        ],
        order_by="from_date asc, creation asc",
    )


@frappe.whitelist()
def compute_item(employee, company=None, month=None, year=None):
    """Tính các tham số dùng cho bảng lương theo kỳ (month, year) và employee."""
    if not month or not year:
        return {}

    employee_info = frappe.db.get_value(
        "Employee",
        employee,
        ["employment_type", "custom_muc_luong_pc_dang", "custom_allowance_coefficient_1"],
        as_dict=True,
    ) or {}

    # 1) Xác định kỳ
    month_str = str(int(month)).zfill(2)
    period_start = getdate(f"{year}-{month_str}-01")
    period_end = get_last_day(period_start)

    # 2) Lấy tham số lương đang hiệu lực (ưu tiên from_date mới nhất trong khoảng)
    salary_param = frappe.get_all(
        "VNT Salary Parameter",
        filters={
            "from_date": ("<=", period_start),
            "to_date": (">=", period_end),
            "docstatus": 1,
        },
        fields=[
            "name",
            "reference_salary",
            "regional_minimum_wage",
            "corporate_minimum_wage",
            "meal_allowance",
            "travel_allowance",
            "giam_tru_npt",
            "giam_tru_gia_canh",
            "tien_gui_xe"
        ],
        order_by="from_date desc",
        limit_page_length=1,
    )
    if not salary_param:
        return
        # frappe.throw("Không tìm thấy bản ghi Tham số lương hiệu lực cho kỳ tính lương này!")
    param = salary_param[0]

    # 3) Tổng hợp Attendance trong kỳ
    #    - Half Day tính 0.5
    #    - 'Ngày công' nếu status = Present
    #        hoặc Half Day nhưng không gắn leave_type
    #    - Còn lại: lấy nhóm từ Leave Type.custom_leave_group
    #    - Có thể lọc theo company nếu Attendance có cột company
    cond_company = "AND a.company = %(company)s" if company else ""
    attendance_sql = f"""
        SELECT
            a.status,
            a.attendance_date,
            a.leave_type,
            COALESCE(lt.custom_leave_group, 'Khác') AS leave_group
        FROM `tabAttendance` a
        LEFT JOIN `tabLeave Type` lt ON lt.name = a.leave_type
        WHERE a.employee = %(employee)s
          AND a.docstatus = 1
          AND a.attendance_date BETWEEN %(start)s AND %(end)s
          {cond_company}
    """
    params = {
        "employee": employee,
        "start": period_start,
        "end": period_end,
    }
    if company:
        params["company"] = company

    attendance_details = frappe.db.sql(attendance_sql, params, as_dict=True)

    group_counts = {}

    def add_group_qty(group_name, qty):
        if qty and qty != 0:
            group_counts[group_name] = group_counts.get(group_name, 0.0) + float(qty)

    WORKING_STATUS_FULL = {"Present", "Work From Home", "On Duty"}
    BUSINESS_TRIP_KEY = "công tác"

    def normalize(value):
        return (value or "").strip().casefold()

    def is_business_trip(record):
        return normalize(record.get("leave_group")) == BUSINESS_TRIP_KEY or normalize(record.get("leave_type")) == BUSINESS_TRIP_KEY

    for att in attendance_details:
        status = (att.status or "").strip()
        leave_group = (att.leave_group or "Khác").strip()
        business_trip = is_business_trip(att)
        qty = 0.5 if status == "Half Day" else 1.0

        if status in WORKING_STATUS_FULL:
            add_group_qty("Ngày công", qty)
        elif status == "Half Day":
            add_group_qty("Ngày công", qty)
            if att.leave_type:
                add_group_qty(leave_group, qty)
        else:
            add_group_qty(leave_group, qty)
            if business_trip:
                add_group_qty("Ngày công", qty)

        if business_trip:
            add_group_qty("Công tác", qty)

    so_phep = group_counts.get("Nghỉ phép", 0.0)
    so_ngay_nghi_vr = group_counts.get("Nghỉ có hưởng lương, chế độ", 0.0)
    nghi_kluong_bhxh_1 = group_counts.get("Nghỉ việc riêng không hưởng lương", 0.0)
    nghi_kluong_bhxh_2 = group_counts.get("Nghỉ hưởng chế độ BHXH", 0.0)
    ngay_cong = group_counts.get("Ngày công", 0.0)
    cong_tac = group_counts.get("Công tác", 0.0)

    # 4) Bậc thuế TNCN (child table)
    #    Sắp xếp theo from_cur tăng dần, chuẩn hoá 'to' = 0 => None (không giới hạn)
    brackets = frappe.get_all(
        "VNT Salary Parameter Item",
        filters={"parent": param.name},
        fields=["percent", "from_cur", "to_cur"],
        order_by="from_cur asc, percent asc",
    )
    tax_brackets = []
    for b in brackets:
        rate = float(b.percent or 0)
        frm = float(b.from_cur or 0)
        to_ = float(b.to_cur or 0)
        tax_brackets.append({
            "rate": rate,          # phần trăm, ví dụ 5, 10, ...
            "from": frm,           # VND
            "to": None if to_ == 0 else to_,  # None = không giới hạn
        })

    contracts = get_employee_contracts(employee, period_start, period_end)
    baseline_date = period_start
    far_future = getdate("9999-12-31")
    salary_history = get_employee_salary_history(employee)

    def ensure_date(value, fallback):
        return getdate(value) if value else fallback

    def find_salary_entry(target_date):
        if not target_date or not salary_history:
            return None
        for entry in reversed(salary_history):
            start_raw = entry.get("from_date")
            if not start_raw:
                continue  # Bỏ qua bản ghi không có từ ngày
            start = ensure_date(start_raw, baseline_date)
            end = ensure_date(entry.get("to_date"), far_future)
            if start <= target_date <= end:
                return entry
        return None

    def find_salary_value(target_date, fieldname):
        entry = find_salary_entry(target_date)
        if not entry:
            return None
        return flt(entry.get(fieldname))

    def find_salary_coefficient(target_date):
        value = find_salary_value(target_date, "he_so")
        return value if value is not None else None

    def find_salary_amount(target_date):
        value = find_salary_value(target_date, "muc_luong")
        return value if value is not None else None

    def find_additional_tax_withholding(target_date):
        entry = find_salary_entry(target_date)
        if not entry:
            return None
        return flt(entry.get("thue_tncn_trich_them"))

    def find_salary_flag(target_date, fieldname):
        entry = find_salary_entry(target_date)
        if not entry:
            return None
        value = entry.get(fieldname)
        if value in (None, ""):
            return None
        return bool(cint(value))

    def annotate_contract(contract):
        if not contract:
            return None, None
        contract_start = ensure_date(contract.get("from_date"), baseline_date)
        contract_end = ensure_date(contract.get("to_date"), far_future)
        overlap_start = max(period_start, contract_start)
        overlap_end = min(period_end, contract_end)
        if overlap_start > overlap_end:
            contract["salary_coefficient"] = None
            return None, None
        contract["salary_coefficient"] = find_salary_coefficient(overlap_start)
        return overlap_start, overlap_end

    contract_types_sorted = sorted(
        contracts,
        key=lambda c: (
            ensure_date(c.get("from_date"), baseline_date),
            c.get("name") or "",
        ),
    )
    current_contract = contract_types_sorted[-1] if contract_types_sorted else None
    previous_contract = (
        contract_types_sorted[-2] if len(contract_types_sorted) > 1 else None
    )
    current_overlap_start, _ = annotate_contract(current_contract)
    previous_overlap_start, _ = annotate_contract(previous_contract)

    current_contract_type = current_contract.get("type") if current_contract else None
    previous_contract_type = previous_contract.get("type") if previous_contract else None
    current_salary_coefficient = find_salary_coefficient(current_overlap_start)
    previous_salary_coefficient = find_salary_coefficient(previous_overlap_start)
    current_salary_amount = find_salary_amount(current_overlap_start)
    previous_salary_amount = find_salary_amount(previous_overlap_start)
    additional_tax_withholding = None

    for candidate_date in (current_overlap_start, period_end, period_start):
        candidate_value = find_additional_tax_withholding(candidate_date)
        if candidate_value is not None:
            additional_tax_withholding = candidate_value
            break

    if additional_tax_withholding is None:
        additional_tax_withholding = 0.0

    def resolve_salary_flag(fieldname, fallback=False):
        for candidate_date in (current_overlap_start, period_end, period_start):
            if not candidate_date:
                continue
            flag = find_salary_flag(candidate_date, fieldname)
            if flag is not None:
                return flag
        return fallback

    skip_meal_allowance = resolve_salary_flag("khong_an_ca", False)
    skip_travel_allowance = resolve_salary_flag("khong_ctp", False)
    flat_tax_10_percent = resolve_salary_flag("thue_tam_trich", False)
    parking_fee_checked = resolve_salary_flag("tien_gui_xe", False)
    parking_fee_amount = flt(param.tien_gui_xe or 0)
    applied_parking_fee = parking_fee_amount if parking_fee_checked else 0.0
    effective_meal_allowance = 0.0 if skip_meal_allowance else flt(param.meal_allowance or 0)
    effective_travel_allowance = 0.0 if skip_travel_allowance else flt(param.travel_allowance or 0)

    total_working_days = float(ngay_cong or 0)
    previous_working_days = 0.0
    current_working_days = total_working_days

    if (
        current_contract
        and previous_contract
        and current_contract.get("from_date")
    ):
        current_from = getdate(current_contract.get("from_date"))
        if period_start <= current_from <= period_end:
            def working_qty(att_row):
                status_local = (att_row.status or "").strip()
                if status_local in WORKING_STATUS_FULL:
                    return 1.0
                if is_business_trip(att_row):
                    return 0.5 if status_local == "Half Day" else 1.0
                if status_local == "Half Day":
                    return 0.5
                return 0.0

            for att in attendance_details:
                qty = working_qty(att)
                if qty <= 0:
                    continue
                att_date = getdate(att.attendance_date)
                if att_date < current_from:
                    previous_working_days += qty

            if previous_working_days > total_working_days:
                previous_working_days = total_working_days
            current_working_days = total_working_days - previous_working_days

    return {
        "reference_salary": param.reference_salary,
        "regional_minimum_wage": param.regional_minimum_wage,
        "corporate_minimum_wage": param.corporate_minimum_wage,
        "meal_allowance": effective_meal_allowance,
        "travel_allowance": effective_travel_allowance,
        "tien_gui_xe": applied_parking_fee,
        "tien_gui_xe_checked": parking_fee_checked,
        "khong_an_ca": skip_meal_allowance,
        "khong_ctp": skip_travel_allowance,
        "thue_tam_trich": flat_tax_10_percent,
        "so_phep": so_phep,
        "cong_tac": cong_tac,
        "so_ngay_nghi_vr": so_ngay_nghi_vr,
        "nghi_kluong_bhxh": (nghi_kluong_bhxh_1 or 0) + (nghi_kluong_bhxh_2 or 0),
        "tax_brackets": tax_brackets,
        "giam_tru_npt": param.giam_tru_npt,
        "giam_tru_gia_canh": param.giam_tru_gia_canh,
        "contracts": contracts,
        "current_contract_type": current_contract_type,
        "previous_contract_type": previous_contract_type,
        "current_working_days": current_working_days,
        "previous_working_days": previous_working_days,
        "ngaycong": total_working_days,
        "current_salary_coefficient": current_salary_coefficient,
        "previous_salary_coefficient": previous_salary_coefficient,
        "latest_salary_coefficient": find_salary_coefficient(period_end) or find_salary_coefficient(period_start),
        "current_salary_amount": current_salary_amount,
        "previous_salary_amount": previous_salary_amount,
        "latest_salary_amount": find_salary_amount(period_end) or find_salary_amount(period_start),
        "thue_tncn_trich_them": flt(additional_tax_withholding),
        "employment_type": employee_info.get("employment_type"),
        "custom_muc_luong_pc_dang": employee_info.get("custom_muc_luong_pc_dang"),
        "custom_allowance_coefficient_1": employee_info.get("custom_allowance_coefficient_1"),
    }


def _get_previous_month_and_year(base_date):
    month = base_date.month - 1
    year = base_date.year
    if month == 0:
        month = 12
        year -= 1
    return month, year


def auto_mark_salary_transferred():
    """Đánh dấu tự động 'Đã chuyển lương' cho bảng lương của tháng liền trước.

    Chạy theo lịch: 05:00 sáng ngày 06 hàng tháng.
    """
    today = getdate()
    target_month, target_year = _get_previous_month_and_year(today)
    month_str = str(int(target_month)).zfill(2)
    year_val = cint(target_year)

    payrolls = frappe.get_all(
        "VNT Monthly Payroll",
        filters={
            "month": month_str,
            "year": year_val,
            "docstatus": 1,
            "da_chuyen_luong": 0,
        },
        pluck="name",
    )

    if not payrolls:
        return

    logger = frappe.logger("vnt_monthly_payroll", allow_site=True)
    logger.info("Auto mark payroll transferred for %s/%s: %s", month_str, year_val, payrolls)

    for name in payrolls:
        try:
            doc = frappe.get_doc("VNT Monthly Payroll", name)
            doc.flags.ignore_permissions = True
            doc.db_set("da_chuyen_luong", 1, update_modified=True, commit=False)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Auto mark salary transferred failed for {name}")


@frappe.whitelist()
def download_payroll_excel(docname=None, type_doc=None):
    """Export bảng lương theo mẫu được chọn."""
    if not docname:
        frappe.throw(_("Thiếu tham chiếu chứng từ để tải xuống."))

    doc = frappe.get_doc("VNT Monthly Payroll", docname)
    selected = (type_doc or doc.type_doc or "").strip()
    if not selected:
        frappe.throw(_("Vui lòng chọn \"Loại biểu mẫu\" trước khi tải xuống."))

    if selected == "Biểu mẫu Bảng tổng":
        filecontent, filename = _build_bang_tong_workbook(doc)
    elif selected == "Biểu mẫu DS chi":
        filecontent, filename = _build_ds_chi_workbook(doc)
    elif selected == "Biểu mẫu BL tháng":
        filecontent, filename = _build_bang_luong_thang_workbook(doc)
    else:
        frappe.throw(_("Loại biểu mẫu {0} chưa được hỗ trợ tải xuống.").format(selected))

    frappe.response["filename"] = filename
    frappe.response["filecontent"] = filecontent
    frappe.response["type"] = "binary"


def _build_bang_tong_workbook(doc):
    """Xuất Excel theo bố cục Biểu mẫu Bảng tổng (có nhóm theo Department)."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Biểu mẫu Bảng tổng"

    columns = [
        {"title": "TT", "field": None, "width": 5, "sum": False, "format": "int"},
        {"title": "Họ và tên", "field": "employee_name", "width": 28, "sum": False, "format": "text"},
        {"title": "Lương cơ bản", "field": "luong_cb", "group": "Lương cơ bản", "width": 14, "sum": True, "format": "currency"},
        {"title": "PC Đảng", "field": "pc_dang1", "group": "Lương cơ bản", "width": 12, "sum": True, "format": "currency"},
        {"title": "PC kiêm nhiệm", "field": "pc_kiem_nhiem1", "group": "Lương cơ bản", "width": 14, "sum": True, "format": "currency"},
        {"title": "Lương tính đóng BHXH", "field": "tong_luong_cb", "group": "Lương cơ bản", "width": 18, "sum": True, "format": "currency"},
        {"title": "Lương tính đóng CĐP", "field": "tong_luong_cb", "group": "Lương phép", "width": 18, "sum": True, "format": "currency"},
        {
            "title": "Số phép",
            "field": "sophep",
            "compute": "sophep_with_vr",
            "group": "Lương phép",
            "width": 10,
            "sum": True,
            "format": "int",
        },
        {"title": "Tiền", "field": "luong_nghiphep_vr", "group": "Lương phép", "width": 12, "sum": True, "format": "currency"},
        {"title": "Nghỉ không lương/ Nghỉ TS Nam", "field": "nghi_kluong_bhxh", "width": 18, "sum": True, "format": "int"},
        {"title": "Ngày công", "field": "ngay_cong", "width": 12, "sum": True, "format": "decimal1"},
        {"title": "Hệ số CBCV", "field": "he_so_cbnv", "group": "Lương CBCV", "width": 12, "sum": False, "format": "decimal2"},
        {"title": "Tiền lương CBCV", "field": "tien_luong_hqcv", "group": "Lương CBCV", "width": 16, "sum": True, "format": "currency"},
        {"title": "PC Đảng", "field": "pc_dang2", "group": "Lương CBCV", "width": 12, "sum": True, "format": "currency"},
        {"title": "PC kiêm nhiệm", "field": "pc_kiem_nhiem2", "group": "Lương CBCV", "width": 14, "sum": True, "format": "currency"},
        {"title": "Tiền lương CQĐH, KTT", "field": "tien_luong_hqcv_cu", "fallback_field": "tien_luong_hqcv", "width": 16, "sum": True, "format": "currency"},
        {"title": "Thù lao HĐQT, BKS", "field": "thu_lao_hdqt", "width": 16, "sum": True, "format": "currency"},
        {"title": "Tiền ăn ca", "field": "tien_an", "width": 12, "sum": True, "format": "currency"},
        {"title": "Tiền khoán công tác phí", "field": "tien_khoan_ct", "width": 18, "sum": True, "format": "currency"},
        {"title": "Truy lĩnh", "field": "truylinh", "width": 12, "sum": True, "format": "currency"},
        {"title": "Tổng thu nhập", "field": "tong_thu_nhap", "width": 16, "sum": True, "format": "currency"},
        {"title": "Bảo hiểm (XH, YT, TN)", "field": "xh_yt_tn", "group": "Các khoản khấu trừ lương", "width": 18, "sum": True, "format": "currency"},
        {"title": "CĐP 0.5%", "field": "doan_phi_cd", "group": "Các khoản khấu trừ lương", "width": 12, "sum": True, "format": "currency"},
        {"title": "Đảng phí 1%", "field": "dang_phi", "group": "Các khoản khấu trừ lương", "width": 12, "sum": True, "format": "currency"},
        {"title": "Thuế TNCN tạm thu", "field": "tncn_tam_thu", "group": "Các khoản khấu trừ lương", "width": 16, "sum": True, "format": "currency"},
        {"title": "Truy thu thuế TNCN 2024", "field": "truy_thu", "group": "Các khoản khấu trừ lương", "width": 18, "sum": True, "format": "currency"},
        {"title": "Thu nhập thực lĩnh", "field": "thuc_linh", "width": 18, "sum": True, "format": "currency"},
        {"title": "Ghi chú", "field": "note", "width": 18, "sum": False, "format": "text"},
    ]

    group_spans = {
        "Lương cơ bản": (3, 6),
        "Lương phép": (7, 9),
        "Lương CBCV": (12, 15),
        "Các khoản khấu trừ lương": (22, 26),
    }

    header_fill = PatternFill("solid", fgColor="D9EAD3")
    total_fill = PatternFill("solid", fgColor="E2EFDA")
    section_fill = PatternFill("solid", fgColor="F2F2F2")
    thin_side = Side(style="thin", color="000000")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, col in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = col.get("width", 12)

    month_label = str(doc.month or "").zfill(2)
    year_label = str(doc.year or "")

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    ws["A1"] = doc.company or "TẬP ĐOÀN DỆT MAY VIỆT NAM"
    ws["A1"].font = Font(bold=True, size=11)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=4)
    branch_text = f"{doc.branch}" if doc.branch else _("Chi nhánh")
    ws["A2"] = branch_text
    ws["A2"].font = Font(size=11)

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(columns))
    ws.cell(row=3, column=1).value = _("BẢNG THANH TOÁN LƯƠNG, THÙ LAO THÁNG {0} NĂM {1}").format(
        month_label, year_label
    )
    ws.cell(row=3, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=3, column=1).font = Font(bold=True, size=14)

    ws.merge_cells(
        start_row=4,
        start_column=max(len(columns) - 2, 1),
        end_row=4,
        end_column=len(columns),
    )
    ws.cell(row=4, column=max(len(columns) - 2, 1)).value = _("Đơn vị tính: đồng")
    ws.cell(row=4, column=max(len(columns) - 2, 1)).alignment = Alignment(horizontal="right", vertical="center")

    group_row = 6
    header_row = 7

    for label, span in group_spans.items():
        start_col, end_col = span
        ws.merge_cells(start_row=group_row, start_column=start_col, end_row=group_row, end_column=end_col)
        ws.cell(row=group_row, column=start_col).value = label

    for idx, col in enumerate(columns, start=1):
        if not col.get("group"):
            ws.merge_cells(start_row=group_row, start_column=idx, end_row=header_row, end_column=idx)
            cell = ws.cell(row=group_row, column=idx)
            if isinstance(cell, MergedCell):
                continue
            cell.value = col["title"]

    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx)
        if isinstance(cell, MergedCell):
            continue
        cell.value = col["title"]

    for row_idx in (group_row, header_row):
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(bold=True, size=11)
            cell.alignment = center_wrap
            cell.fill = header_fill
            cell.border = thin_border

    ws.row_dimensions[group_row].height = 36
    ws.row_dimensions[header_row].height = 38

    data_start_row = header_row + 1
    current_row = data_start_row
    items = list(doc.get("items") or [])

    groups = [
        {"key": "HDQT", "roman": "I", "label": _("Hội đồng quản trị")},
        {"key": "BKS", "roman": "II", "label": _("Ban kiểm soát")},
        {"key": "DIEU_HANH", "roman": "III", "label": _("Cơ quan điều hành")},
        {"key": "CM_IV1", "roman": "IV.1", "label": _("Các ban chuyên môn")},
        {"key": "CM_IV2", "roman": "IV.2", "label": _("Các ban Đảng")},
        {"key": "CM_IV3", "roman": "IV.3", "label": _("Vinatex Coats")},
        {"key": "CONG_DOAN", "roman": "V", "label": _("Công đoàn")},
    ]

    def resolve_cell_value(row_data, col_idx, col):
        fmt = col.get("format")
        if col.get("compute") == "sophep_with_vr":
            return cint(flt(row_data.get("sophep") or 0) + flt(row_data.get("so_ngay_nghi_vr") or 0))
        if col.get("field"):
            raw_value = row_data.get(col["field"])
            if (raw_value in (None, "", 0)) and col.get("fallback_field"):
                fallback_val = row_data.get(col["fallback_field"])
                raw_value = fallback_val if fallback_val not in (None, "") else raw_value
            if fmt in {"currency", "decimal1", "decimal2"}:
                return flt(raw_value or 0)
            if fmt == "int":
                return cint(raw_value or 0)
            return raw_value
        return None

    sum_columns = {col_idx: col for col_idx, col in enumerate(columns, start=1) if col.get("sum")}
    group_totals = {g["key"]: {idx: 0 for idx in sum_columns} for g in groups}

    def categorize_department(value):
        norm = _strip_vietnamese_accents(value or "")
        if "CONG DOAN" in norm:
            return "CONG_DOAN"
        if "HOI DONG QUAN TRI" in norm or "HDQT" in norm:
            return "HDQT"
        if "KIEM SOAT" in norm or "BKS" in norm:
            return "BKS"
        if "DIEU HANH" in norm or "KTT" in norm:
            return "DIEU_HANH"
        ban_dang_keywords = [
            "CO QUAN UY BAN KIEM TRA",
            "VAN PHONG DANG UY",
            "BAN TUYEN GIAO DANG UY",
            "BAN TO CHUC DANG UY",
        ]
        if any(keyword in norm for keyword in ban_dang_keywords):
            return "CM_IV2"
        if "COATS" in norm or "CHONG CHAY" in norm:
            return "CM_IV3"
        return "CM_IV1"

    for item in items:
        group_key = categorize_department(item.get("department"))
        totals = group_totals.get(group_key)
        if totals is None:
            continue
        row_data = item.as_dict()
        for col_idx, col in sum_columns.items():
            val = resolve_cell_value(row_data, col_idx, col)
            totals[col_idx] += flt(val or 0)

    overall_totals = {idx: 0 for idx in sum_columns}
    for totals in group_totals.values():
        for idx, val in totals.items():
            overall_totals[idx] += val

    for grp in groups:
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.border = thin_border
            if col_idx == 1:
                cell.value = grp["roman"]
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = Font(bold=True)
            elif col_idx == 2:
                cell.value = grp["label"]
                cell.font = Font(bold=True)
            elif col_idx in sum_columns:
                cell.value = group_totals.get(grp["key"], {}).get(col_idx, 0)
                fmt = sum_columns[col_idx].get("format")
                if fmt == "currency":
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif fmt == "decimal1":
                    cell.number_format = "0.0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif fmt == "decimal2":
                    cell.number_format = "0.00"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif fmt == "int":
                    cell.number_format = "0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
        current_row += 1

    last_data_row = current_row - 1 if items else header_row
    total_row = last_data_row + 1

    ws.cell(row=total_row, column=2).value = _("Tổng cộng")
    ws.cell(row=total_row, column=2).font = Font(bold=True)

    for col_idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=total_row, column=col_idx)
        if col.get("sum"):
            cell.value = overall_totals.get(col_idx, 0)
            fmt = col.get("format")
            if fmt == "currency":
                cell.number_format = "#,##0"
            elif fmt == "decimal1":
                cell.number_format = "0.0"
            elif fmt == "decimal2":
                cell.number_format = "0.00"
            elif fmt == "int":
                cell.number_format = "0"
            cell.alignment = Alignment(horizontal="right", vertical="center")
        elif col_idx == 2:
            cell.alignment = Alignment(horizontal="left", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="center", vertical="center")

        cell.border = thin_border
        cell.fill = total_fill
        cell.font = Font(bold=True)

    ws.freeze_panes = f"A{data_start_row}"

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = f"bang-luong-bang-tong-{month_label}-{year_label or 'nam'}.xlsx"
    return output.getvalue(), filename


def _build_ds_chi_workbook(doc):
    """Xuất Excel theo bố cục Danh sách chi lương (mẫu DS chi)."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "DS Chi"

    columns = [
        {"key": "idx", "title": "TT", "width": 6, "align": "center"},
        {"key": "account_no", "title": "Số tài khoản", "width": 18, "align": "center"},
        {"key": "currency", "title": "Loại tiền", "width": 10, "align": "center"},
        {"key": "beneficiary", "title": "Tên Người hưởng", "width": 26, "align": "left"},
        {"key": "amount", "title": "Số tiền", "width": 16, "align": "right", "number_format": "#,##0"},
        {"key": "content", "title": "Nội dung", "width": 34, "align": "left"},
        {
            "key": "transfer_mode",
            "title": "Chuyển tiền nhanh 24/7/ Chuyển tiền thường ngoài VCB",
            "width": 24,
            "align": "center",
        },
        {"key": "bank_name", "title": "Tại ngân hàng", "width": 18, "align": "center"},
        {"key": "note", "title": "Ghi chú", "width": 16, "align": "left"},
    ]

    header_fill = PatternFill("solid", fgColor="E2EFDA")
    thin_side = Side(style="thin", color="000000")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, col in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = col.get("width", 12)

    month_label = str(doc.month or "").zfill(2)
    year_label = str(doc.year or "")

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
    ws["A1"] = (doc.company or "TẬP ĐOÀN DỆT MAY VIỆT NAM").upper()
    ws["A1"].font = Font(bold=True, size=11)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=3)
    branch_text = (doc.branch or _("Văn phòng")).upper()
    ws["A2"] = branch_text
    ws["A2"].font = Font(size=11)

    ws.merge_cells(start_row=3, start_column=6, end_row=3, end_column=len(columns))
    ref_cell = ws.cell(row=3, column=6)
    ref_cell.value = _("Số tham chiếu LTT: .............................. -{0}/{1}-............").format(
        month_label, year_label
    )
    ref_cell.alignment = Alignment(horizontal="right", vertical="center")

    ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=len(columns))
    title_cell = ws.cell(row=5, column=1)
    title_cell.value = _("BẢNG THANH TOÁN CHI LƯƠNG THÁNG {0}/{1}").format(month_label, year_label)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    title_cell.font = Font(bold=True, size=14)

    ws.merge_cells(start_row=6, start_column=max(len(columns) - 1, 1), end_row=6, end_column=len(columns))
    unit_cell = ws.cell(row=6, column=max(len(columns) - 1, 1))
    unit_cell.value = _("Đơn vị tính: đồng")
    unit_cell.alignment = Alignment(horizontal="right", vertical="center")

    header_row = 7
    for col_idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=col["title"])
        cell.font = Font(bold=True)
        cell.alignment = center_wrap
        cell.fill = header_fill
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 32

    content_template = _("Vinatex chi lương, thù lao tháng {0}/{1}").format(month_label, year_label)
    data_start_row = header_row + 1
    items = list(doc.get("items") or [])

    for idx, item in enumerate(items, start=1):
        account_no = (item.get("bank_ac_name") or item.get("bank_ac_no") or "") or ""
        beneficiary = _strip_vietnamese_accents(item.get("employee_name") or item.get("employee") or "")
        row_data = {
            "idx": idx,
            "account_no": account_no.strip() if hasattr(account_no, "strip") else account_no,
            "currency": "VND",
            "beneficiary": beneficiary,
            "amount": flt(item.get("thuc_linh") or 0),
            "content": content_template,
            "transfer_mode": "",
            "bank_name": (item.get("bank_name") or "").strip(),
            "note": item.get("note") or "",
        }

        current_row = data_start_row + idx - 1
        for col_idx, col in enumerate(columns, start=1):
            value = row_data.get(col["key"])
            cell = ws.cell(row=current_row, column=col_idx, value=value)
            cell.border = thin_border

            align_key = col.get("align", "left")
            if align_key == "center":
                alignment = Alignment(horizontal="center", vertical="center")
            elif align_key == "right":
                alignment = Alignment(horizontal="right", vertical="center")
            else:
                alignment = Alignment(horizontal="left", vertical="center")
            cell.alignment = alignment

            if col.get("number_format") and value not in (None, ""):
                cell.number_format = col["number_format"]

    ws.freeze_panes = f"A{data_start_row}"

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = f"bang-luong-ds-chi-{month_label}-{year_label or 'nam'}.xlsx"
    return output.getvalue(), filename


def _build_bang_luong_thang_workbook(doc):
    """Xuất Excel theo mẫu Bảng lương tháng (hiển thị từng nhân sự, nhóm theo phòng/ban)."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "BL tháng"

    columns = [
        {"title": "TT", "field": None, "width": 5, "format": "int"},
        {"title": "Họ và tên", "field": "employee_name", "width": 22, "format": "text"},
        {"title": "Tên chủ tài khoản", "field": "bank_ac_name", "fallback_field": "employee_name", "width": 22, "format": "text"},
        {"title": "Số tài khoản", "field": "bank_ac_no", "width": 16, "format": "text"},
        {"title": "Giới tính", "field": "gender", "width": 9, "format": "text"},
        {"title": "Không đóng BHXH", "field": "bhxh", "width": 14, "format": "text"},
        {"title": "Hệ số", "field": "hs_luong_cb", "group": "Lương cơ bản", "width": 10, "format": "decimal2"},
        {"title": "Lương cơ bản", "field": "luong_cb", "group": "Lương cơ bản", "width": 14, "sum": True, "format": "currency"},
        {"title": "PC Đảng", "field": "pc_dang1", "group": "Lương cơ bản", "width": 12, "sum": True, "format": "currency"},
        {"title": "PC kiêm nhiệm", "field": "pc_kiem_nhiem1", "group": "Lương cơ bản", "width": 14, "sum": True, "format": "currency"},
        {"title": "Lương tính đóng BHXH + BNN", "field": "tong_luong_cb", "group": "Lương cơ bản", "width": 18, "sum": True, "format": "currency"},
        {"title": "Lương tính đóng CĐP", "field": "tong_luong_cb", "group": "Lương cơ bản", "width": 16, "sum": True, "format": "currency"},
        {"title": "Số phép", "field": "sophep", "compute": "sophep_with_vr", "group": "Lương phép", "width": 10, "sum": True, "format": "int"},
        {"title": "Tiền", "field": "luong_nghiphep_vr", "group": "Lương phép", "width": 12, "sum": True, "format": "currency"},
        {"title": "Nghỉ việc riêng có hưởng lương", "field": "so_ngay_nghi_vr", "width": 18, "sum": True, "format": "int"},
        {"title": "Nghỉ TS Nam", "field": "nghi_kluong_bhxh", "width": 12, "sum": True, "format": "int"},
        {"title": "Ngày công", "field": "ngay_cong", "width": 12, "sum": True, "format": "decimal1"},
        {"title": "Hệ số CBCV", "field": "he_so_cbnv", "group": "Lương CBCV", "width": 12, "format": "decimal2"},
        {"title": "Tiền lương CBCV", "field": "tien_luong_hqcv", "group": "Lương CBCV", "width": 16, "sum": True, "format": "currency"},
        {"title": "PC Đảng", "field": "pc_dang2", "group": "Lương CBCV", "width": 12, "sum": True, "format": "currency"},
        {"title": "PC kiêm nhiệm", "field": "pc_kiem_nhiem2", "group": "Lương CBCV", "width": 14, "sum": True, "format": "currency"},
        {"title": "Tiền lương CQĐH, KTT", "field": "tien_luong_hqcv_cu", "fallback_field": "tien_luong_hqcv", "group": "Lương CBCV", "width": 16, "sum": True, "format": "currency"},
        {"title": "Thù lao HDQT, BKS", "field": "thu_lao_hdqt", "width": 16, "sum": True, "format": "currency"},
        {"title": "Tiền khoán công tác phí", "field": "tien_khoan_ct", "width": 18, "sum": True, "format": "currency"},
        {"title": "Truy lĩnh", "field": "truylinh", "width": 12, "sum": True, "format": "currency"},
        {"title": "Tổng thu nhập", "field": "tong_thu_nhap", "width": 16, "sum": True, "format": "currency"},
        {"title": "Thu nhập chịu thuế", "field": "tong_tn_chiu_thue", "fallback_field": "thu_nhap_tinh_thue", "width": 16, "sum": True, "format": "currency"},
        {"title": "Trừ BHXH 10.5%", "field": "xh_yt_tn", "group": "Các khoản khấu trừ lương", "width": 16, "sum": True, "format": "currency"},
        {"title": "Trừ BHYT 1.5%", "field": "tru_bhyt", "group": "Các khoản khấu trừ lương", "width": 14, "sum": True, "format": "currency"},
        {"title": "Thu hồi BHXH/BN/TNS", "field": "tru_bhtn", "group": "Các khoản khấu trừ lương", "width": 18, "sum": True, "format": "currency"},
        {"title": "CĐP 0.5%", "field": "doan_phi_cd", "group": "Các khoản khấu trừ lương", "width": 12, "sum": True, "format": "currency"},
        {"title": "Đảng phí 1%", "field": "dang_phi", "group": "Các khoản khấu trừ lương", "width": 12, "sum": True, "format": "currency"},
        {"title": "Thu nhập tính thuế", "field": "thu_nhap_tinh_thue", "group": "Các khoản tính thuế", "width": 16, "sum": True, "format": "currency"},
        {"title": "Thuế TNCN tạm thu", "field": "tncn_tam_thu", "group": "Các khoản tính thuế", "width": 16, "sum": True, "format": "currency"},
        {"title": "Khác", "field": "khac", "group": "Các khoản tính thuế", "width": 12, "sum": True, "format": "currency"},
        {"title": "Truy thu thuế TNCN 2024", "field": "truy_thu", "group": "Các khoản tính thuế", "width": 18, "sum": True, "format": "currency"},
        {"title": "Thu nhập thực lĩnh", "field": "thuc_linh", "width": 16, "sum": True, "format": "currency"},
        {"title": "Thực lĩnh hàng lẻ", "field": "thuc_linh_le", "width": 16, "sum": False, "format": "currency"},
        {"title": "Ghi chú", "field": "note", "width": 18, "format": "text"},
    ]

    group_spans = {
        "Lương cơ bản": (7, 12),
        "Lương phép": (13, 14),
        "Lương CBCV": (18, 22),
        "Các khoản khấu trừ lương": (28, 32),
        "Các khoản tính thuế": (33, 36),
    }

    header_fill = PatternFill("solid", fgColor="D9EAD3")
    total_fill = PatternFill("solid", fgColor="E2EFDA")
    section_fill = PatternFill("solid", fgColor="F2F2F2")
    thin_side = Side(style="thin", color="000000")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, col in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = col.get("width", 12)

    month_label = str(doc.month or "").zfill(2)
    year_label = str(doc.year or "")

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    ws["A1"] = doc.company or "TẬP ĐOÀN DỆT MAY VIỆT NAM"
    ws["A1"].font = Font(bold=True, size=11)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=5)
    branch_text = f"{doc.branch}" if doc.branch else _("Chi nhánh")
    ws["A2"] = branch_text
    ws["A2"].font = Font(size=11)

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(columns))
    ws.cell(row=3, column=1).value = _("BẢNG THANH TOÁN LƯƠNG, THÙ LAO THÁNG {0} NĂM {1}").format(
        month_label, year_label
    )
    ws.cell(row=3, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=3, column=1).font = Font(bold=True, size=14)

    ws.merge_cells(
        start_row=4,
        start_column=max(len(columns) - 2, 1),
        end_row=4,
        end_column=len(columns),
    )
    ws.cell(row=4, column=max(len(columns) - 2, 1)).value = _("Đơn vị tính: đồng")
    ws.cell(row=4, column=max(len(columns) - 2, 1)).alignment = Alignment(horizontal="right", vertical="center")

    group_row = 6
    header_row = 7

    for label, span in group_spans.items():
        start_col, end_col = span
        ws.merge_cells(start_row=group_row, start_column=start_col, end_row=group_row, end_column=end_col)
        ws.cell(row=group_row, column=start_col).value = label

    for idx, col in enumerate(columns, start=1):
        if not col.get("group"):
            ws.merge_cells(start_row=group_row, start_column=idx, end_row=header_row, end_column=idx)
            ws.cell(row=group_row, column=idx).value = col["title"]

    for idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=idx)
        if isinstance(cell, MergedCell):
            continue
        cell.value = col["title"]

    for row_idx in (group_row, header_row):
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(bold=True, size=11)
            cell.alignment = center_wrap
            cell.fill = header_fill
            cell.border = thin_border

    ws.row_dimensions[group_row].height = 36
    ws.row_dimensions[header_row].height = 38

    data_start_row = header_row + 1
    current_row = data_start_row
    items = list(doc.get("items") or [])

    group_defs = [
        {"key": "HDQT", "roman": "I", "label": _("Hội đồng quản trị")},
        {"key": "BKS", "roman": "II", "label": _("Ban kiểm soát")},
        {"key": "DIEU_HANH", "roman": "III", "label": _("Cơ quan điều hành")},
        {"key": "CM_IV1", "roman": "IV.1", "label": _("Các ban chuyên môn")},
        {"key": "CM_IV2", "roman": "IV.2", "label": _("Các ban Đảng")},
        {"key": "CM_IV3", "roman": "IV.3", "label": _("Vinatex Coats")},
        {"key": "CONG_DOAN", "roman": "V", "label": _("Công đoàn")},
    ]

    def categorize_department(value):
        norm = _strip_vietnamese_accents(value or "")
        if "CONG DOAN" in norm:
            return "CONG_DOAN"
        if "HOI DONG QUAN TRI" in norm or "HDQT" in norm:
            return "HDQT"
        if "KIEM SOAT" in norm or "BKS" in norm:
            return "BKS"
        if "DIEU HANH" in norm or "KTT" in norm:
            return "DIEU_HANH"
        ban_dang_keywords = [
            "CO QUAN UY BAN KIEM TRA",
            "VAN PHONG DANG UY",
            "BAN TUYEN GIAO DANG UY",
            "BAN TO CHUC DANG UY",
        ]
        if any(keyword in norm for keyword in ban_dang_keywords):
            return "CM_IV2"
        if "COATS" in norm or "CHONG CHAY" in norm:
            return "CM_IV3"
        return "CM_IV1"

    def _clean_dept_label(label):
        if not label:
            return _("Khác")
        text = (label or "").strip()
        for suffix in [" - VGT", "- VGT", "-VGT", " – VGT", "– VGT"]:
            if text.upper().endswith(suffix.strip().upper()):
                text = text[: -len(suffix)].rstrip(" -–")
                break
        return text or _("Khác")

    buckets = {g["key"]: [] for g in group_defs}
    for item in items:
        dept_label = _clean_dept_label(item.get("department"))
        buckets.setdefault(categorize_department(item.get("department")), []).append((dept_label, item))

    def _salary_cbcv_value(item):
        try:
            he_so = flt(item.get("he_so_cbnv") if hasattr(item, "get") else getattr(item, "he_so_cbnv", 0) or 0)
            if he_so != 0:
                return he_so
            return flt(item.get("tien_luong_hqcv") if hasattr(item, "get") else getattr(item, "tien_luong_hqcv", 0) or 0)
        except Exception:
            return 0

    for key in list(buckets.keys()):
        buckets[key] = sorted(buckets[key], key=lambda tup: _salary_cbcv_value(tup[1]), reverse=True)

    def resolve_cell_value(row_data, col_idx, col):
        fmt = col.get("format")
        if col_idx == 1:
            return row_data.get("_row_number")
        if col.get("compute") == "sophep_with_vr":
            return cint(flt(row_data.get("sophep") or 0) + flt(row_data.get("so_ngay_nghi_vr") or 0))
        if col.get("field"):
            raw_value = row_data.get(col["field"])
            if (raw_value in (None, "", 0)) and col.get("fallback_field"):
                fallback_val = row_data.get(col["fallback_field"])
                raw_value = fallback_val if fallback_val not in (None, "") else raw_value
            if fmt in {"currency", "decimal1", "decimal2"}:
                return flt(raw_value or 0)
            if fmt == "int":
                return cint(raw_value or 0)
            return raw_value
        return None

    sum_columns = {col_idx: col for col_idx, col in enumerate(columns, start=1) if col.get("sum")}
    running_index = 0

    for grp in group_defs:
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.border = thin_border
            cell.fill = section_fill
        ws.cell(row=current_row, column=1).value = grp["roman"]
        ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row=current_row, column=1).font = Font(bold=True)
        ws.cell(row=current_row, column=2).value = grp["label"]
        ws.cell(row=current_row, column=2).font = Font(bold=True)
        current_row += 1

        if grp["key"] != "CM_IV1":
            for dept_label, item in buckets.get(grp["key"], []):
                running_index += 1
                row_data = item.as_dict()
                row_data["_row_number"] = running_index
                for col_idx, col in enumerate(columns, start=1):
                    value = resolve_cell_value(row_data, col_idx, col)
                    fmt = col.get("format")

                    cell = ws.cell(row=current_row, column=col_idx, value=value)
                    cell.border = thin_border

                    alignment = Alignment(horizontal="right", vertical="center")
                    if fmt == "text":
                        alignment = Alignment(horizontal="left", vertical="center")
                    if col_idx == 1:
                        alignment = Alignment(horizontal="center", vertical="center")
                    cell.alignment = alignment

                    if fmt == "currency":
                        cell.number_format = "#,##0"
                    elif fmt == "decimal1":
                        cell.number_format = "0.0"
                    elif fmt == "decimal2":
                        cell.number_format = "0.00"
                    elif fmt == "int":
                        cell.number_format = "0"

                current_row += 1
        else:
            dept_map = {}
            for dept_label, item in buckets.get(grp["key"], []):
                dept_map.setdefault(dept_label, []).append(item)

            for dept_label in sorted(dept_map.keys()):
                dept_items = sorted(dept_map[dept_label], key=_salary_cbcv_value, reverse=True)
                for col_idx in range(1, len(columns) + 1):
                    cell = ws.cell(row=current_row, column=col_idx)
                    cell.border = thin_border
                    if col_idx == 2:
                        cell.value = dept_label
                        cell.font = Font(bold=True, italic=True)
                    elif col_idx == 1:
                        cell.value = ""
                    cell.fill = section_fill
                current_row += 1

                for item in dept_items:
                    running_index += 1
                    row_data = item.as_dict()
                    row_data["_row_number"] = running_index
                    for col_idx, col in enumerate(columns, start=1):
                        value = resolve_cell_value(row_data, col_idx, col)
                        fmt = col.get("format")

                        cell = ws.cell(row=current_row, column=col_idx, value=value)
                        cell.border = thin_border

                        alignment = Alignment(horizontal="right", vertical="center")
                        if fmt == "text":
                            alignment = Alignment(horizontal="left", vertical="center")
                        if col_idx == 1:
                            alignment = Alignment(horizontal="center", vertical="center")
                        cell.alignment = alignment

                        if fmt == "currency":
                            cell.number_format = "#,##0"
                        elif fmt == "decimal1":
                            cell.number_format = "0.0"
                        elif fmt == "decimal2":
                            cell.number_format = "0.00"
                        elif fmt == "int":
                            cell.number_format = "0"

                    current_row += 1

    last_data_row = current_row - 1 if items else header_row
    total_row = last_data_row + 1

    ws.cell(row=total_row, column=2).value = _("Tổng cộng")
    ws.cell(row=total_row, column=2).font = Font(bold=True)

    for col_idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=total_row, column=col_idx)
        if col.get("sum") and items:
            col_letter = get_column_letter(col_idx)
            cell.value = f"=SUM({col_letter}{data_start_row}:{col_letter}{last_data_row})"
            fmt = col.get("format")
            if fmt == "currency":
                cell.number_format = "#,##0"
            elif fmt == "decimal1":
                cell.number_format = "0.0"
            elif fmt == "decimal2":
                cell.number_format = "0.00"
            elif fmt == "int":
                cell.number_format = "0"
            cell.alignment = Alignment(horizontal="right", vertical="center")
        elif col_idx == 2:
            cell.alignment = Alignment(horizontal="left", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="center", vertical="center")

        cell.border = thin_border
        cell.fill = total_fill
        cell.font = Font(bold=True)

    ws.freeze_panes = f"A{data_start_row}"

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = f"bang-luong-bl-thang-{month_label}-{year_label or 'nam'}.xlsx"
    return output.getvalue(), filename


def _strip_vietnamese_accents(value):
    """Loại bỏ dấu tiếng Việt và in hoa tên phục vụ xuất DS chi."""
    if not value:
        return ""
    text = value.strip()
    # Map riêng Đ/đ vì normalize không bỏ được
    text = text.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_diacritics.upper()


def _to_roman(number):
    """Đổi số tự nhiên sang chữ số La Mã (dùng đánh dấu nhóm Department)."""
    if not number or number <= 0:
        return ""
    mapping = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result = []
    for value, symbol in mapping:
        while number >= value:
            result.append(symbol)
            number -= value
    return "".join(result)
