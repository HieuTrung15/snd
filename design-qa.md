# Design QA — Sơ đồ tổ chức

## Evidence

- Source truth: the reference organization-chart screenshots attached in the user request (no local filesystem path was exposed to the workspace).
- Implementation render: `/tmp/vnt-org-chart-continuous-lines.png` at 2048 × 980, rendered from the production chart HTML structure and `vnt_organization_chart.css`.
- Runtime route: `/app/vnt-organization-chart` on site `hrmsnd.vinatex.com.vn`.

## Comparison

The implementation render was visually inspected against the supplied reference. It shows one factory heading, the director/deputy relationship, four departments, the orange maintenance branch and green production branch. The production hierarchy is now `Sản xuất trực tiếp → Trưởng ca → Bông chải/Ghép thô/Máy con/Máy ống`; every vertical connector overlaps its horizontal junction so the paths are continuous through browser pixel rounding. The requested role chains remain visible as `Trưởng CĐ → Phó trưởng CĐ → CN bảo toàn` and `Tổ trưởng SX → Tổ phó SX → CN công nghệ`. `Kỹ thuật`, `Vào bông`, and `Nhặt bông` are absent from the active chart. Department count badges are not rendered.

## Functional checks

- API source contains 73 active nodes in Nested Set order (76 retained records, including three disabled obsolete nodes).
- Tree integrity: one root, `lft/rgt` range 1–152, four production processes parented by `Trưởng ca`, and sampled role chains have the expected parents.
- Workspace shortcut opens the chart Page directly.
- Employee has read/select access; edit action remains limited to users with write permission.
- The chart CSS is loaded through the standard Page stylesheet instead of the asynchronous JavaScript asset loader, so a stylesheet problem cannot leave Frappe's loading overlay frozen.
- Python unit tests, Python compilation, JavaScript syntax checks, JSON validation, and `git diff --check` pass.

## Result

**BLOCKED for strict side-by-side visual sign-off.** The source screenshots supplied through the conversation are not available as local image files, and the environment has no authenticated browser runtime. The production CSS/HTML render passed manual inspection, but a valid comparison image containing both source and live browser output cannot be produced in this environment.
