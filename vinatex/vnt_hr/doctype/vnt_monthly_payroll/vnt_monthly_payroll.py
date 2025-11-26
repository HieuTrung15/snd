# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, flt, get_first_day, get_last_day, getdate, now_datetime


class VNTMonthlyPayroll(Document):
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
          AND (from_date IS NULL OR from_date <= %(period_end)s)
          AND (to_date IS NULL OR to_date >= %(period_start)s)
        ORDER BY
            COALESCE(from_date, DATE('1900-01-01')),
            name
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
        fields=["name", "he_so", "from_date", "to_date", "muc_luong"],
        order_by="from_date asc, creation asc",
    )


@frappe.whitelist()
def compute_item(employee, company=None, month=None, year=None):
    """Tính các tham số dùng cho bảng lương theo kỳ (month, year) và employee."""
    if not month or not year:
        return {}

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
    baseline_date = getdate("1900-01-01")
    far_future = getdate("9999-12-31")
    salary_history = get_employee_salary_history(employee)

    def ensure_date(value, fallback):
        return getdate(value) if value else fallback

    def find_salary_entry(target_date):
        if not target_date or not salary_history:
            return None
        for entry in reversed(salary_history):
            start = ensure_date(entry.get("from_date"), baseline_date)
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
        "meal_allowance": param.meal_allowance,
        "travel_allowance": param.travel_allowance,
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
    }
