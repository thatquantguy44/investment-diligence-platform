#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

# This wrapper only prepares an explicitly analyst-approved release. It never
# calls ingest-uspto-bulk and intentionally leaves promotion as a separate step.
exec python -m diligence_pipelines.cli refresh-uspto-odp "$@"
