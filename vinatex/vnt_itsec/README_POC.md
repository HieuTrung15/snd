# VNT IT Security POC (CVE Sync + Matching)

This POC builds a lightweight CVE database inside the existing vinatex app.
It supports three sources (CVELISTV5, NVD, OSV), nightly sync, and basic
matching of CVE CPEs to IT assets.

## 1) Install / Bootstrap

Run the bootstrap on a site (creates doctypes, roles, sources):

```bash
bench --site YOUR_SITE execute vinatex.vnt_itsec.install.bootstrap
```

Or use the helper script:

```bash
vinatex/vnt_itsec/scripts/poc_bootstrap.sh YOUR_SITE
```

Notes:
- No user accounts are created; create users manually as needed.
- Companies/departments are not auto-created; prepare them before loading sample data.

If the app is newly installed, `after_install` runs the bootstrap once.

## 2) Configure site_config.json

Edit `sites/YOUR_SITE/site_config.json` and add:

```json
{
  "vnt_itsec_nvd_api_key": "",
  "vnt_itsec_cvelistv5_path": "/home/frappe/vnt_itsec_data/cvelistV5",
  "vnt_itsec_osv_enabled": 1,
  "vnt_itsec_osv_queries": [],
  "vnt_itsec_alert_email": "sonph@vinatex.com.vn",
  "vnt_itsec_store_only_matched": 1,
  "vnt_itsec_cve_retention_days": 30
}
```

Notes:
- NVD API key is optional but recommended to avoid rate limits.
- The cvelistV5 repo path must be readable by the bench user.
- `vnt_itsec_osv_queries` accepts JSON array for OSV querybatch payload (fallback uses POC sample packages).
- `vnt_itsec_alert_email` receives automation summary emails.
- When `vnt_itsec_store_only_matched=1`, cleanup removes CVEs not linked to affected assets.
- `vnt_itsec_cve_retention_days` controls the cutoff for periodic cleanup (days).

## 3) Clone cvelistV5 repo

```bash
mkdir -p /home/frappe/vnt_itsec_data
cd /home/frappe/vnt_itsec_data
git clone https://github.com/CVEProject/cvelistV5.git
```

## 4) Run a manual sync

```bash
bench --site YOUR_SITE execute vinatex.vnt_itsec.sync.run.run_nightly
```

Expected:
- `VNT CVE` contains records
- `published_date` / `last_modified_date` are source timestamps
- `first_seen_at` is the local ingest time
- Matching + remediation ticket creation run automatically after nightly sync.

## 5) Enable nightly scheduler

Scheduler is wired in `vinatex/hooks.py` (01:30 daily).

```bash
bench --site YOUR_SITE enable-scheduler
bench restart
```

## 6) UI quick tour

- Workspace: `VNT IT Security` (module shortcut)
- Dashboard page: `itsec-dashboard`
- Buttons:
  - `VNT CVE Source`: Run Sync Now
  - `VNT Vulnerability Advisory`: Run Matching
  - `VNT CVE`: Open NVD

If new JS/CSS were added, run:

```bash
bench build --app vinatex
bench restart
```

## 7) Quick matching test

1) Create an IT Asset with a Software Component whose CPE matches a CVE.
2) Create a VNT Vulnerability Advisory and add a CVE.
3) Run matching:

```bash
bench --site YOUR_SITE execute vinatex.vnt_itsec.matching.match.run_matching_for_advisory --kwargs "{'advisory_name': 'ADV-2025-12-0001'}"
```

## 8) Source toggle

Use `VNT CVE Source` to enable/disable sources and control limits:
- enabled
- max_per_run
- sync_mode (FULL/INCREMENTAL)

## 9) POC notes

- CVE timestamps are always from source payloads, not from sync time.
- OSV in POC uses a static package list; replace with your SBOM list later.
- cvelistV5 FULL sync can be heavy; use `max_per_run` to cap initial load.
