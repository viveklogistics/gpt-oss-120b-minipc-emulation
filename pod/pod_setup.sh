#!/usr/bin/env bash
# Runs ON THE RUNPOD POD (Ubuntu 24.04, CUDA 12.8 PyTorch template). Started automatically by runpod_ctl.py,
# or by hand:  bash pod_setup.sh   (log: /pod_setup.log when started by runpod_ctl.py)
# 1) arms an in-pod self-destruct timer  2) fetches llama.cpp CUDA 12.8 binaries (builds from source if that fails)
# 3) downloads gpt-oss-120b MXFP4 GGUF (~63 GB)  4) starts llama-server --jinja on port 8000  5) health-checks it.
set -uo pipefail
LLAMA_TAG="${LLAMA_TAG:-b12024}"                 # pinned build checked on 1 Nov 2026; falls back to newest if missing
MODEL_REPO="${MODEL_REPO:-ggml-org/gpt-oss-120b-GGUF}"
MODEL_FILE="${MODEL_FILE:-gpt-oss-120b-MXFP4.gguf}"
CTX="${CTX:-32768}"; PORT="${PORT:-8000}"; AUTO_STOP_HOURS="${AUTO_STOP_HOURS:-3}"
W=/workspace; mkdir -p $W/models $W/llama; cd $W
log(){ echo "[$(date -u +%H:%M:%S)Z] $*"; }
STATUS=$W/setup_status.txt; echo "starting" > $STATUS

# ---- 1. self-destruct timer inside the pod (second safety net; runpod_ctl.py also runs one on your side)
if [ -n "${RUNPOD_POD_ID:-}" ]; then
  STOP_S=$(awk "BEGIN{print int(${AUTO_STOP_HOURS}*3600)}")
  nohup bash -c "sleep $STOP_S; echo 'AUTO-STOP reached' ;
    runpodctl remove pod $RUNPOD_POD_ID || runpodctl pod delete $RUNPOD_POD_ID || runpodctl stop pod $RUNPOD_POD_ID ||
    curl -s -X DELETE -H \"Authorization: Bearer \$RUNPOD_API_KEY\" https://rest.runpod.io/v1/pods/$RUNPOD_POD_ID ||
    curl -s -X POST -H \"Authorization: Bearer \$RUNPOD_API_KEY\" https://rest.runpod.io/v1/pods/$RUNPOD_POD_ID/stop" \
    > $W/autostop.log 2>&1 &
  log "in-pod auto-stop armed: ${AUTO_STOP_HOURS} h = ${STOP_S}s (pod $RUNPOD_POD_ID)"
fi

nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
command -v curl >/dev/null || (apt-get update -qq && apt-get install -y -qq curl)

# ---- 2. llama.cpp CUDA binaries (prebuilt, ~0.8 GB) -> build from source as fallback
get_prebuilt(){
  local tag="$1"; local base="https://github.com/ggml-org/llama.cpp/releases/download/$tag"
  curl -fsSL -o /tmp/llama.tgz "$base/llama-$tag-bin-ubuntu-cuda-12.8-x64.tar.gz" &&
  curl -fsSL -o /tmp/cudart.tgz "$base/cudart-llama-$tag-bin-ubuntu-cuda-12.8-x64.tar.gz" &&
  tar -xzf /tmp/llama.tgz -C $W/llama && tar -xzf /tmp/cudart.tgz -C $W/llama
}
( log "downloading llama.cpp $LLAMA_TAG"
  if ! get_prebuilt "$LLAMA_TAG"; then
    T=$(curl -fsSL "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=5" | python3 -c \
       "import json,sys;print(next(r['tag_name'] for r in json.load(sys.stdin) if r['tag_name'].startswith('b')))")
    log "pinned tag failed, trying $T"; get_prebuilt "$T" || true
  fi ) &
PID_BIN=$!

# ---- 3. model download in parallel (the slow part)
( log "downloading $MODEL_REPO/$MODEL_FILE"
  pip install -q -U "huggingface_hub[hf_xet]" >/dev/null 2>&1
  if command -v hf >/dev/null && hf download "$MODEL_REPO" "$MODEL_FILE" --local-dir $W/models; then :;
  else curl -fL -C - -o "$W/models/$MODEL_FILE" "https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE"; fi
  log "model download finished: $(du -h $W/models/$MODEL_FILE | cut -f1)" ) &
PID_MODEL=$!

wait $PID_BIN
SERVER=$(find $W/llama -name llama-server -type f | head -1)
if [ -z "$SERVER" ] || ! LD_LIBRARY_PATH="$(dirname "$SERVER"):${LD_LIBRARY_PATH:-}" "$SERVER" --version >/dev/null 2>&1; then
  log "prebuilt binary unusable -> building from source (~10 min)"; echo "building" > $STATUS
  apt-get update -qq && apt-get install -y -qq git cmake build-essential libcurl4-openssl-dev >/dev/null
  git clone --depth 1 https://github.com/ggml-org/llama.cpp $W/llama-src
  cmake -S $W/llama-src -B $W/llama-src/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build $W/llama-src/build -j"$(nproc)" --target llama-server
  SERVER=$W/llama-src/build/bin/llama-server
fi
export LD_LIBRARY_PATH="$(dirname "$SERVER"):${LD_LIBRARY_PATH:-}"
log "llama-server: $SERVER ($("$SERVER" --version 2>&1 | head -2 | tr '\n' ' '))"

wait $PID_MODEL
[ -s "$W/models/$MODEL_FILE" ] || { log "MODEL DOWNLOAD FAILED"; echo "model_download_failed" > $STATUS; exit 1; }

# ---- 4. start the server (all layers on GPU, one slot so the whole context is available; CTX env, default 32k)
#         if the requested context does not fit in VRAM, fall back once to 65536
start_server() {
  echo "loading" > $STATUS
  nohup "$SERVER" -m "$W/models/$MODEL_FILE" --jinja -c "$1" -ngl 99 -np 1 --host 0.0.0.0 --port "$PORT" \
        --metrics > $W/llama_server.log 2>&1 &
  echo $! > $W/llama_server.pid; log "llama-server starting with -c $1"
}
start_server "$CTX"

# ---- 5. health check (model load takes 1-3 min)
for i in $(seq 1 150); do
  if curl -fs "http://127.0.0.1:$PORT/health" | grep -q ok; then
    log "llama-server healthy after $((i*5)) s (ctx $CTX)"; echo "ready" > $STATUS
    curl -s "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' \
      -d '{"messages":[{"role":"user","content":"Reply with the word ready."}],"max_tokens":64}' | head -c 600; echo
    exit 0
  fi
  if ! kill -0 "$(cat $W/llama_server.pid)" 2>/dev/null && [ "$CTX" -gt 65536 ]; then
    log "llama-server exited with ctx $CTX (likely out of VRAM); tail:"; tail -15 $W/llama_server.log
    CTX=65536; start_server "$CTX"
  fi
  sleep 5
done
log "llama-server did not become healthy; tail of log:"; tail -40 $W/llama_server.log; echo "server_failed" > $STATUS; exit 1
