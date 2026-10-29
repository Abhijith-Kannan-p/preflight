#!/usr/bin/env bash
# Run the backend in a container with Render's free-plan limits (512 MB RAM, no swap, 0.1 CPU)
# and the production settings from render.yaml, then time each stage and read memory: the
# server's peak resident memory, and the cgroup's anonymous, file-cache and peak memory.
#
#   docker compose up -d db            # Postgres with pgvector
#   bash deploy/render-sim.sh          # from the repository root
#
# The LLM is off (no API key enters the container); everything else matches production.
set -euo pipefail

NAME=pf-render-sim
PORT=8100
API="http://127.0.0.1:${PORT}"
DB=preflight_sim

docker build -q -f backend/Dockerfile -t preflight-render-sim . >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker compose exec -T db psql -U preflight -d preflight -qc "DROP DATABASE IF EXISTS ${DB};" -c "CREATE DATABASE ${DB};" >/dev/null
docker run -d --name "$NAME" --network preflight_default --memory=512m --memory-swap=512m --cpus=0.1 \
  -p "${PORT}:7860" -v pfmodels:/app/.cache/huggingface \
  -e DATABASE_URL="postgresql+psycopg://preflight:preflight@db:5432/${DB}" \
  -e NLI_BACKEND=onnx -e MODEL_LOADING=lazy -e NLI_BATCH_SIZE=2 -e EVAL_AT_BOOT=precomputed \
  -e REVIEW_WORKERS=1 -e OCR_EXCLUSIVE=true -e OCR_THREADS=1 -e MALLOC_ARENA_MAX=2 \
  -e HF_HUB_OFFLINE=1 -e LLM_PROVIDER=none -e JWT_SECRET=sim -e SANDBOX_COOKIE_SECURE=false \
  preflight-render-sim >/dev/null

# MSYS_NO_PATHCONV: Git Bash on Windows would otherwise rewrite the /sys and /proc paths.
in_box() { MSYS_NO_PATHCONV=1 docker exec "$NAME" sh -c "$1"; }
mib() { echo $(( $(in_box "cat /sys/fs/cgroup/$1") / 1048576 )); }
stat() { in_box "grep '^$1 ' /sys/fs/cgroup/memory.stat" | awk '{print int($2/1048576)}'; }
# The server process's own peak resident memory (VmHWM of PID 1: uvicorn, after exec).
hwm() { in_box "grep VmHWM /proc/1/status" | awk '{print int($2/1024)}'; }
# The cgroup peak also counts reclaimable file cache (the model files), so it can reach the
# limit without risk; "anon" is the memory that cannot be given back.
report() {
  printf '%-32s %6s s | process peak %4s MiB | anon %4s, file cache %4s MiB | cgroup peak %4s MiB\n' \
    "$1" "$2" "$(hwm)" "$(stat anon)" "$(stat file)" "$(mib memory.peak)"
}
json() { python -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
now() { date +%s.%N; }
since() { python -c "print(round($(now) - $1, 1))"; }

start=$(now)
until curl -sf -m 3 "$API/health" >/dev/null 2>&1; do sleep 3; done
report "server up (cold start)" "$(since "$start")"
# The demo history (36 reviews) is generated in the background after start-up.
while true; do
  count=$(docker compose exec -T db psql -U preflight -d "$DB" -tAc "select count(*) from submissions" 2>/dev/null || echo 0)
  [ "${count:-0}" -ge 36 ] && break
  sleep 5
done
report "demo history generated" "$(since "$start")"

session() { curl -s -X POST "$API/api/sandbox/session" -H 'content-type: application/json' -d '{}' | json "d['token']"; }
TOKEN=$(session)
AUTH=(-H "Authorization: Bearer ${TOKEN}")

wait_review() {  # id -> seconds until the review is no longer pending
  local id=$1 t0; t0=$(now)
  while [ "$(curl -s "$API/api/reviews/$id" "${AUTH[@]}" | json "d['revision']['review_status']")" = "pending" ]; do sleep 2; done
  since "$t0"
}

id=$(curl -s -X POST "$API/api/reviews" "${AUTH[@]}" -F channel=linkedin -F sample_id=sample_linkedin | json "d['id']")
report "text review, first (models load)" "$(wait_review "$id")"
id=$(curl -s -X POST "$API/api/reviews" "${AUTH[@]}" -F channel=linkedin \
  -F "content=PayWise settles merchant payments in under 5 seconds and is 100% secure! Ref $(now)" | json "d['id']")
report "text review, warm" "$(wait_review "$id")"
id=$(curl -s -X POST "$API/api/reviews" "${AUTH[@]}" -F channel=linkedin -F sample_id=sample_festive_banner | json "d['id']")
report "visual review (festive banner)" "$(wait_review "$id")"

ADMIN=$(curl -s -X POST "$API/api/auth/demo-login" -H 'content-type: application/json' -d '{"user_id":"usr_abhi3"}' | json "d['token']")
t0=$(now)
job=$(curl -s -X POST "$API/api/compiler/jobs" -H "Authorization: Bearer ${ADMIN}" -F use_sample=true | json "d['id']")
while [ "$(curl -s "$API/api/compiler/jobs/$job" -H "Authorization: Bearer ${ADMIN}" | json "d['status']")" = "running" ]; do sleep 2; done
report "brand book compiled (no LLM)" "$(since "$t0")"
t0=$(now)
curl -s "$API/api/voice/fingerprint" -H "Authorization: Bearer ${ADMIN}" >/dev/null
report "voice fingerprint" "$(since "$t0")"

t0=$(now)
pids=()
for n in 1 2 3 4 5; do
  (
    tok=$(session)
    rid=$(curl -s -X POST "$API/api/reviews" -H "Authorization: Bearer $tok" -F channel=linkedin \
      -F "content=Visitor $n: PayWise is the fastest app and settles in under 3 seconds! Ref $(now)" | json "d['id']")
    while [ "$(curl -s "$API/api/reviews/$rid" -H "Authorization: Bearer $tok" | json "d['revision']['review_status']")" = "pending" ]; do sleep 2; done
    echo "  visitor $n done after $(since "$t0") s"
  ) &
  pids+=($!)
done
wait "${pids[@]}"
report "five concurrent reviews" "$(since "$t0")"
docker inspect "$NAME" --format 'container: {{.State.Status}}, OOM killed: {{.State.OOMKilled}}, restarts: {{.RestartCount}}'
