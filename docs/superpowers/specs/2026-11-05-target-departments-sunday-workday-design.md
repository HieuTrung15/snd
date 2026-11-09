# Target Departments Sunday Workday Design

## Intent

Employees whose current Department is exactly `Vào bông - NMSVNĐ` or
`Công đoạn Đóng gói - NMSVNĐ` work on Sundays. A Sunday represented by a
Holiday row with `weekly_off = 1` must therefore be classified as a workday,
not an OFF day, whenever the employee has a non-OFF planned shift window.

## Goals

- Apply one shared classification consistently to attendance confirmation,
  Attendance processing, monthly reports, and leadership dashboards.
- Keep strict IN/OUT presence-only confirmation for the two Departments on
  `Hành chính`: complete IN+OUT needs no explanation; missing one side or all
  Checkins still requires explanation.
- Refresh unresolved confirmations for `2026-10-01..2026-11-04` after the
  policy is active.

## Non-goals

- Do not change Employee Checkin records.
- Do not reinterpret public/company holidays where `weekly_off = 0`.
- Do not turn an explicitly planned OFF window into a workday.
- Do not change Sunday behavior for any other Department.

## Constraints

- Use the current `Employee.department` value and the two exact Department
  names; no prefix or fuzzy matching.
- The exception applies to `weekly_off = 1` only and requires a planned window
  whose `is_off` value is false.
- Preserve confirmed attendance-confirmation rows as audit history.
- Never evaluate the current or a future calendar date.
- Keep all source changes local on branch `develop`; do not commit or push.

## Approaches

1. **Approved: shared classifier policy.** Extend `classify_work_date` so every
   existing consumer receives the same Sunday result. This avoids disagreement
   between confirmations, reports, Attendance processing, and dashboards.
2. Confirmation-only exception. Rejected because reports and Attendance would
   continue to label the same day as OFF.
3. Department-specific Holiday Lists. Rejected because each year and each new
   Employee would require manual assignment and maintenance.

## Expected Historical Result

The existing 44 unresolved Sunday `OFF_WITH_CHECKIN` rows for the two target
Departments are reevaluated. Complete IN+OUT pairs disappear; incomplete or
missing pairs become the appropriate workday issue. Existing non-Sunday
workday issues and public-holiday behavior remain unchanged.
