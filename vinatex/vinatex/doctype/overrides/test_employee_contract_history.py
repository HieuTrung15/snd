from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vinatex.doctype.overrides.employee import VntEmployee


class ContractHistoryEmployee:
    def __init__(self, values, previous=None, contracts=None):
        self.values = values
        self.previous = frappe._dict(previous) if previous is not None else None
        self.contracts = [frappe._dict(row) for row in (contracts or [])]
        self.appended = []

    def get_doc_before_save(self):
        return self.previous

    def get(self, fieldname):
        if fieldname == "custom_vnt_contract":
            return self.contracts
        return self.values.get(fieldname)

    def append(self, fieldname, values):
        assert fieldname == "custom_vnt_contract"
        row = frappe._dict(values)
        self.contracts.append(row)
        self.appended.append(row)
        return row


class TestEmployeeContractHistory(TestCase):
    @patch(
        "vinatex.vinatex.doctype.overrides.employee._get_current_director_name",
        return_value="Phạm Ngọc Bình",
    )
    def test_appends_mapped_contract_when_employment_type_changes(self, get_director):
        current_contract = {"type": "Hợp đồng thử việc", "validity": 1}
        employee = ContractHistoryEmployee(
            {
                "company": "Nhà máy Sợi Vinatex Nam Định",
                "employment_type": "HĐLĐ xác định thời hạn",
                "custom_appointment_date": "2026-10-13",
                "contract_end_date": "2027-10-12",
                "designation": "Nhân viên Nhân sự",
            },
            previous={"employment_type": "Hợp đồng thử việc"},
            contracts=[current_contract],
        )

        VntEmployee._append_contract_when_employment_type_changes(employee)

        self.assertEqual(employee.contracts[0].validity, 0)
        self.assertEqual(
            employee.appended,
            [
                {
                    "type": "HĐLĐ xác định thời hạn",
                    "from_date": "2026-10-13",
                    "to_date": "2027-10-12",
                    "job_title": "Nhân viên Nhân sự",
                    "employee_name": "Phạm Ngọc Bình",
                    "validity": 1,
                }
            ],
        )
        get_director.assert_called_once_with("Nhà máy Sợi Vinatex Nam Định")

    @patch("vinatex.vinatex.doctype.overrides.employee._get_current_director_name")
    def test_does_nothing_when_employment_type_is_unchanged(self, get_director):
        employee = ContractHistoryEmployee(
            {"employment_type": "HĐLĐ xác định thời hạn"},
            previous={"employment_type": "HĐLĐ xác định thời hạn"},
        )

        VntEmployee._append_contract_when_employment_type_changes(employee)

        self.assertEqual(employee.appended, [])
        get_director.assert_not_called()

    @patch("vinatex.vinatex.doctype.overrides.employee._get_current_director_name")
    def test_clearing_employment_type_does_not_create_empty_contract(self, get_director):
        employee = ContractHistoryEmployee(
            {"employment_type": None},
            previous={"employment_type": "Hợp đồng thử việc"},
        )

        VntEmployee._append_contract_when_employment_type_changes(employee)

        self.assertEqual(employee.appended, [])
        get_director.assert_not_called()
