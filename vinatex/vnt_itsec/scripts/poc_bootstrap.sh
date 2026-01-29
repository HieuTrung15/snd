#!/usr/bin/env bash
set -euo pipefail

SITE="${1:-}"

if [[ -z "${SITE}" ]]; then
  echo "Usage: $(basename "$0") <site>"
  exit 1
fi

bench --site "${SITE}" execute vinatex.vnt_itsec.install.bootstrap
bench --site "${SITE}" execute vinatex.vnt_itsec.sync.run.run_nightly
