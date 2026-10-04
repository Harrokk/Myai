#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export MYAI_SETTINGS="config/profiles/ventuno_q.json"

exec python3 mail.py
