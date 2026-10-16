from __future__ import unicode_literals

from erpnext.setup.doctype.holiday_list.holiday_list import HolidayList


class VntHolidayList(HolidayList):
    """Keep standard Holiday List behavior without global data mutation.

    The previous override updated every active Employee and Company whenever a
    Holiday List was inserted. That behavior is intentionally removed because
    Holiday Lists for different Kíp must coexist and legacy assignments must
    remain unchanged. Explicit Kíp linking lives in ``holiday_service``.
    """

    pass
