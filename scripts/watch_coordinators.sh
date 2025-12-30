#!/usr/bin/env bash
set -euo pipefail

# Genera/actualiza servers.json para Traefik con los coordinadores vivos.
# Usa SEEDS (coma separada) como puntos de partida y recopila /health y /leaders.

OUT=${OUT:-$(pwd)/servers.json}
SEEDS=${SEEDS:-}
INTERVAL=${INTERVAL:-5}

if [[ -z "$SEEDS" ]]; then
  echo "❌ Debes exportar SEEDS con las URLs de coordinadores conocidos, ej:" >&2
  echo "   SEEDS=\"http://192.168.20.112:8700,http://192.168.20.147:8701\" bash $0" >&2
  exit 1
fi

echo "▶️ Watcher de coordinadores. Archivo: $OUT | Intervalo: ${INTERVAL}s"
echo "   Seeds: $SEEDS"

while true; do
  python3 - "$OUT" "$SEEDS" <<'PYCODE'
import sys, json, urllib.request
from urllib.error import URLError

out, seeds_raw = sys.argv[1], sys.argv[2]
seeds = [s.strip() for s in seeds_raw.split(",") if s.strip()]
urls = set()

for seed in seeds:
    # /health para saber si está vivo y es coordinador
    try:
        with urllib.request.urlopen(f"{seed}/health", timeout=2) as resp:
            data = json.load(resp)
            if data.get("service") == "coordinator":
                urls.add(seed)
    except Exception:
        pass

# Si no quedó nada, usa seeds para no vaciar el LB
if not urls:
    urls = set(seeds)

servers = [{"url": u} for u in sorted(urls)]
config = {
    "http": {
        "routers": {
            "coordinator": {"rule": "PathPrefix(`/`)", "service": "coordinators"}
        },
        "services": {
            "coordinators": {
                "loadBalancer": {"servers": servers, "passHostHeader": True}
            }
        },
    }
}
with open(out, "w") as f:
    json.dump(config, f, indent=2)
PYCODE
  sleep "$INTERVAL"
done
