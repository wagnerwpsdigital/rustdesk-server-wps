#!/bin/bash
# Sobe um hbbs local novo (db/chaves descartáveis em run/), roda o teste de protocolo e derruba o hbbs pelo PID que ele mesmo criou.
set -u
cd "$(dirname "$0")"
BIN=${1:-../../target/release/hbbs}
rm -rf run && mkdir run
( cd run && RUST_LOG=info exec "../$BIN" -p 31116 > hbbs.log 2>&1 ) &
PID=$!
sleep 2
.venv/bin/python test_ws_register.py ws://127.0.0.1:31118 "$(cat run/id_ed25519.pub)"
RC=$?
kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
grep -E "peer (registered|disconnected)|panick" run/hbbs.log
exit $RC
