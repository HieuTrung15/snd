from __future__ import unicode_literals

import frappe
from frappe import _
from hrms.hr.doctype.attendance.attendance import (
	Attendance
)
from datetime import datetime, date, time, timedelta
from frappe.utils import getdate, now_datetime

STANDARD_START_TIME = time(8, 17)
STANDARD_END_TIME = time(17, 0)


class VntAttendance(Attendance):
	pass


@frappe.whitelist()
def create_attendance_from_checkin():
	"""
	Loop qua tất cả employee active và tạo Attendance từ đầu tháng đến ngày hiện tại.
	Tối ưu để tránh timeout khi chạy cron.
	"""
	# Lấy ngày hiện tại
	date = now_datetime().date()
	# start_date = date.replace(day=1)  # Đầu tháng
	start_date = date.replace(month=9, day=1)
	# Lấy danh sách employee active một lần
	employees = frappe.get_all('Employee', 
		filters={'status': 'Active', 'custom_need_check': 0}, 
		fields=['name', 'employee_name', 'company', 'department', 'holiday_list']
	)
	
	if not employees:
		return
	
	# Tạo list tất cả ngày cần xử lý
	date_list = []
	current_date = start_date
	while current_date <= date:
		date_list.append(current_date)
		current_date += timedelta(days=1)
	
	# Lấy tất cả Attendance đã tồn tại trong khoảng thời gian
	existing_attendances = set()
	existing_att_data = frappe.get_all('Attendance', 
		filters={
			'attendance_date': ['between', [start_date, date]],
			'docstatus': 1
		},
		fields=['employee', 'attendance_date']
	)
	for att in existing_att_data:
		existing_attendances.add((att.employee, att.attendance_date))
	
	# Lấy tất cả Leave Applications trong khoảng thời gian
	leave_data = frappe.get_all('Leave Application', 
		filters={
			'docstatus': 1,
			'from_date': ['<=', date],
			'to_date': ['>=', start_date]
		},
		fields=['employee', 'from_date', 'to_date']
	)
	
	# Tạo dict leave theo employee
	employee_leaves = {}
	for leave in leave_data:
		if leave.employee not in employee_leaves:
			employee_leaves[leave.employee] = []
		employee_leaves[leave.employee].append({
			'from_date': getdate(leave.from_date),
			'to_date': getdate(leave.to_date)
		})
	
	# Lấy tất cả holidays theo holiday_list
	holiday_data = frappe.get_all('Holiday', fields=['parent', 'holiday_date'])
	holiday_lists = {}
	for holiday in holiday_data:
		if holiday.parent not in holiday_lists:
			holiday_lists[holiday.parent] = set()
		holiday_lists[holiday.parent].add(getdate(holiday.holiday_date))
	
	# Lấy tất cả checkin data trong khoảng thời gian
	checkin_data = frappe.db.sql("""
		SELECT 
			employee,
			DATE(time) as checkin_date,
			MIN(CASE WHEN log_type = 'IN' THEN time END) as in_time,
			MAX(CASE WHEN log_type = 'OUT' THEN time END) as out_time
		FROM `tabEmployee Checkin`
		WHERE DATE(time) BETWEEN %s AND %s
		AND log_type IN ('IN', 'OUT')
		GROUP BY employee, DATE(time)
	""", (start_date, date), as_dict=True)
	# frappe.throw(F"{checkin_data}")
	# Tạo dict checkin theo employee và date
	employee_checkins = {}
	for checkin in checkin_data:
		emp_key = checkin.employee
		date_key = getdate(checkin.checkin_date)
		if emp_key not in employee_checkins:
			employee_checkins[emp_key] = {}
		employee_checkins[emp_key][date_key] = {
			'in_time': checkin.in_time,
			'out_time': checkin.out_time
		}
	
	# Batch insert attendances
	attendances_to_create = []
	
	# Xử lý employees có checkin
	for emp in employees:
		emp_name = emp['name']
		emp_leaves = employee_leaves.get(emp_name, [])
		emp_holidays = holiday_lists.get(emp['holiday_list'], set()) if emp.get('holiday_list') else set()
		emp_checkins = employee_checkins.get(emp_name, {})
		
		for current_date in date_list:
			# Skip nếu đã có attendance
			if (emp_name, current_date) in existing_attendances:
				continue
			
			# Skip nếu là ngày nghỉ lễ
			if current_date in emp_holidays:
				continue
			
			# Skip nếu trong kỳ nghỉ phép
			is_leave_day = any(
				leave['from_date'] <= current_date <= leave['to_date'] 
				for leave in emp_leaves
			)
			if is_leave_day:
				continue
			
			# Lấy checkin data
			checkin_info = emp_checkins.get(current_date)
			if not checkin_info or not (checkin_info['in_time'] and checkin_info['out_time']):
				continue

			in_time = checkin_info['in_time'].time() if isinstance(checkin_info['in_time'], datetime) else checkin_info['in_time']
			out_time = checkin_info['out_time'].time() if isinstance(checkin_info['out_time'], datetime) else checkin_info['out_time']
			if (in_time and in_time > STANDARD_START_TIME) or (out_time and out_time < STANDARD_END_TIME):
				# Bỏ qua các bản ghi đi muộn / về sớm để xử lý thủ công
				continue
			
			# Thêm vào list để tạo
			attendances_to_create.append({
				'doctype': 'Attendance',
				'employee': emp_name,
				'employee_name': emp['employee_name'],
				'company': emp['company'],
				'attendance_date': current_date,
				'status': 'Present',
				'shift': 'Hành chính',
				'docstatus': 1
			})
	
	# Xử lý employees có custom_need_check = 1 (không cần checkin)
	emp_not_checkin = frappe.get_all('Employee', 
		filters={'status': 'Active', 'custom_need_check': 1}, 
		fields=['name', 'employee_name', 'company', 'department', 'holiday_list']
	)
	
	for emp in emp_not_checkin:
		emp_name = emp['name']
		emp_leaves = employee_leaves.get(emp_name, [])
		emp_holidays = holiday_lists.get(emp['holiday_list'], set()) if emp.get('holiday_list') else set()
		
		for current_date in date_list:
			# Skip nếu đã có attendance
			if (emp_name, current_date) in existing_attendances:
				continue
			
			# Skip nếu là ngày nghỉ lễ
			if current_date in emp_holidays:
				continue
			
			# Skip nếu trong kỳ nghỉ phép
			is_leave_day = any(
				leave['from_date'] <= current_date <= leave['to_date'] 
				for leave in emp_leaves
			)
			if is_leave_day:
				continue
			
			# Thêm vào list để tạo
			attendances_to_create.append({
				'doctype': 'Attendance',
				'employee': emp_name,
				'employee_name': emp['employee_name'],
				'company': emp['company'],
				'attendance_date': current_date,
				'status': 'Present',
				'shift': 'Hành chính',
				'docstatus': 1
			})
	
	# Batch insert tất cả attendance
	if attendances_to_create:
		# Chia nhỏ batch để tránh timeout
		batch_size = 100
		for i in range(0, len(attendances_to_create), batch_size):
			batch = attendances_to_create[i:i + batch_size]
			try:
				frappe.db.bulk_insert('Attendance', 
					fields=['doctype', 'employee', 'employee_name', 'company', 'attendance_date', 'status', 'shift', 'docstatus'],
					values=[[att[field] for field in ['doctype', 'employee', 'employee_name', 'company', 'attendance_date', 'status', 'shift', 'docstatus']] for att in batch]
				)
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(f"Error inserting attendance batch: {str(e)}", "Attendance Batch Insert Error")
				# Fallback: insert từng record
				for att_data in batch:
					try:
						att = frappe.new_doc('Attendance')
						for key, value in att_data.items():
							if key != 'doctype':
								setattr(att, key, value)
						att.save()
						att.submit()
					except Exception as individual_error:
						frappe.log_error(f"Error creating attendance for {att_data.get('employee')} on {att_data.get('attendance_date')}: {str(individual_error)}", "Individual Attendance Error")
	
	return len(attendances_to_create)


def _get_employee_checkin(employee, date=None):
	"""
	DEPRECATED: Sử dụng query tổng hợp trong create_attendance_from_checkin thay thế
	"""
	if not date:
		date = now_datetime().date()
	else:
		date = getdate(date)
	
	start_date = datetime.combine(date, datetime.min.time())
	end_date = datetime.combine(date, datetime.max.time())
	
	# Query MIN IN time
	in_time = frappe.db.sql("""
		SELECT MIN(time) as min_time
		FROM `tabEmployee Checkin`
		WHERE employee = %s
		AND log_type = 'IN'
		AND time >= %s
		AND time <= %s
	""", (employee, start_date, end_date), as_dict=1)
	
	in_time = in_time[0]['min_time'] if in_time and in_time[0]['min_time'] else None
	
	# Query MAX OUT time
	out_time = frappe.db.sql("""
		SELECT MAX(time) as max_time
		FROM `tabEmployee Checkin`
		WHERE employee = %s
		AND log_type = 'OUT'
		AND time >= %s
		AND time <= %s
	""", (employee, start_date, end_date), as_dict=1)
	
	out_time = out_time[0]['max_time'] if out_time and out_time[0]['max_time'] else None
	return in_time, out_time
