#!/usr/bin/env bash
set -euo pipefail

docker rm -f coordinator_lb 2>/dev/null || true
echo "Balanceador detenido y eliminado."
