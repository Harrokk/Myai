#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export MYAI_SETTINGS="config/profiles/ventuno_q.json"

python3 scripts/validate_config.py --ventuno

exec python3 scripts/ventuno_runtime.py
