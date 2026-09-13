#!/usr/bin/env bash
# Start the connected local demonstration; Ctrl+C stops processes started here.
set -euo pipefail
workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace_root"
mkdir -p .runtime
children=()
cleanup() {
  for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT TERM
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules || ! -d blockchain/node_modules ]]; then
  echo 'Install first: make install; npm --prefix frontend ci; npm --prefix blockchain ci' >&2
  exit 1
fi
make migrate bootstrap
if ! curl --silent --fail --max-time 2 -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' http://127.0.0.1:8545 >/dev/null; then
  (cd blockchain && exec node node_modules/ganache/dist/node/cli.js --server.host 127.0.0.1 --chain.chainId 1337 --wallet.deterministic --database.dbPath .chain --logging.quiet) >.runtime/blockchain.log 2>&1 &
  children+=("$!")
  for _ in {1..30}; do
    if curl --silent --fail --max-time 1 -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' http://127.0.0.1:8545 >/dev/null; then break; fi
    sleep 1
  done
fi
(cd blockchain && npm run deploy)
if ! curl --silent --fail --max-time 2 http://127.0.0.1:8000/health/ready >/dev/null; then
  .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 >.runtime/api.log 2>&1 &
  children+=("$!")
fi
if ! curl --silent --fail --max-time 2 http://127.0.0.1:5173 >/dev/null; then
  (cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) >.runtime/frontend.log 2>&1 &
  children+=("$!")
fi
for _ in {1..30}; do
  if curl --silent --fail --max-time 1 http://127.0.0.1:8000/health/ready >/dev/null && curl --silent --fail --max-time 1 http://127.0.0.1:5173 >/dev/null; then
    echo 'UrjaSetu: http://127.0.0.1:5173 | API: http://127.0.0.1:8000/docs'
    echo 'Use the demo sign-in buttons. Open private windows for different people.'
    echo 'Logs: .runtime/ | Data and local chain persist between runs.'
    if ((${#children[@]})); then wait -n "${children[@]}"; fi
    exit 0
  fi
  sleep 1
done
echo 'Startup failed. Inspect .runtime/api.log and .runtime/frontend.log.' >&2
exit 1
