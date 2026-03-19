#!/usr/bin/env bash
set -euo pipefail
cd /root/.openclaw/workspace/projects/ths-trend-eod-strategy
TRADE_DATE="${1:-$(date +%F)}"
python3 run_fullchain_test.py --date "$TRADE_DATE"
