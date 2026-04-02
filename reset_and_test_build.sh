#!/usr/bin/env bash
set -euo pipefail

cd /home/rhizoid/code/apical-event

export HOST="172.16.0.145"
export PORT="8420"

rm -rf data/

docker compose down
docker compose up --build -d

sleep 2

echo "Waiting for /api/health..."
for i in {1..30}; do
  if curl -s -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}/api/health" | grep -q "200"; then
    echo "Health check OK"
    break
  fi
  sleep 1
done

curl -s -X POST "http://${HOST}:${PORT}/api/sessions/init" \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/valid_packet.json | tee tmp/session.json
echo ""

python3 - <<'PY'
import json
with open("tmp/session.json", "r") as f:
    data = json.load(f)
print("SESSION_ID:", data["session_id"])
print("URL:", data["url"])
PY

export SESSION_ID="$(python3 - <<'PY'
import json
print(json.load(open("tmp/session.json"))["session_id"])
PY
)"

SESSION_DIR=""
echo "Waiting for session files to appear..."
while [ -z "${SESSION_DIR}" ]; do
  SESSION_DIR="$(find data/projects -type d -path "*/sessions/${SESSION_ID}" 2>/dev/null | head -n 1)"
  sleep 1
done
STATE_PATH="${SESSION_DIR}/state.json"
JOURNAL_GLOB="${SESSION_DIR}/journals/*_journal.json"

last_dump=""
while true; do
  current_dump="$(python3 - <<'PY'
import json, glob, os
state_path=os.environ.get("STATE_PATH")
journal_glob=os.environ.get("JOURNAL_GLOB")
parts=[]
if state_path and os.path.exists(state_path):
    state=json.load(open(state_path))
    parts.append(f"state={state.get('state')} substate={state.get('substate')} chat={len(state.get('chat_history',[]))} actions={len(state.get('pending_action_cards',[]))} quizzes={len(state.get('pending_quizzes',[]))} error={state.get('error')}")
if journal_glob:
    for path in sorted(glob.glob(journal_glob)):
        data=json.load(open(path))
        turns=data.get('turns', [])
        last=turns[-1]['turn_type'] if turns else None
        parts.append(f"{data.get('agent_id')}: turns={len(turns)} last={last}")
print(" | ".join(parts))
PY
)"
  if [ "${current_dump}" != "${last_dump}" ]; then
    echo "=== $(date) ==="
    echo "${current_dump}"
    last_dump="${current_dump}"
  fi
  sleep 1
done
