#!/usr/bin/env bash
set -euo pipefail
cd /workspace/TracePaper
python -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.lock
npm --prefix web ci --cache /workspace/.npm --no-audit --no-fund
npm --prefix web run build
