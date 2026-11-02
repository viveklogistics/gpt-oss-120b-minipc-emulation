#!/usr/bin/env bash
# ON THE POD. Emulates a consumer mini PC (64 GB DDR4, 10C/16T i7-13620H class) + 22 GB and 12 GB eGPUs for gpt-oss-120b MXFP4.
# Results served read-only on port 8002 (8001 is taken by the image nginx) (/workspace/out). Synthetic data only.
set -uo pipefail
LLAMA_TAG="${LLAMA_TAG:-b12024}"; MODEL_REPO=ggml-org/gpt-oss-120b-GGUF; MODEL_FILE=gpt-oss-120b-MXFP4.gguf
CTX=65536; PORT=8000; AUTO_STOP_HOURS="${AUTO_STOP_HOURS:-4}"; CAP0=22016; CAP1=11776   # MiB (21.5 / 11.5 GiB)
W=/workspace; O=$W/out; M=$W/models/$MODEL_FILE; mkdir -p $W/models $W/llama $O; cd $W
log(){ echo "[$(date -u +%H:%M:%S)Z] $*" | tee -a $O/progress.log; }
st(){ echo "$*" > $O/status.txt; log "STATUS $*"; }
st starting
(cd $O && nohup python3 -m http.server 8002 >/dev/null 2>&1 &)
if [ -n "${RUNPOD_POD_ID:-}" ]; then
  STOP_S=$(awk "BEGIN{print int(${AUTO_STOP_HOURS}*3600)}")
  nohup bash -c "sleep $STOP_S; runpodctl remove pod $RUNPOD_POD_ID || curl -s -X DELETE -H \"Authorization: Bearer \$RUNPOD_API_KEY\" https://rest.runpod.io/v1/pods/$RUNPOD_POD_ID" > $W/autostop.log 2>&1 &
  log "in-pod auto-stop armed ${AUTO_STOP_HOURS} h"
fi
NPROC=$(nproc)
{ echo "nproc=$NPROC"; lscpu | grep -E "Model name|Socket|Core|Thread|NUMA node\(s\)|MHz"; free -g; swapon --show; echo "--cgroup";
  cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null; cat /sys/fs/cgroup/cpu.max 2>/dev/null
  nvidia-smi --query-gpu=index,name,memory.total,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max --format=csv; } > $O/sysinfo.txt 2>&1

# ---- downloads in background
get_prebuilt(){ local b="https://github.com/ggml-org/llama.cpp/releases/download/$1"
  curl -fsSL -o /tmp/l.tgz "$b/llama-$1-bin-ubuntu-cuda-12.8-x64.tar.gz" && curl -fsSL -o /tmp/c.tgz "$b/cudart-llama-$1-bin-ubuntu-cuda-12.8-x64.tar.gz" &&
  tar -xzf /tmp/l.tgz -C $W/llama && tar -xzf /tmp/c.tgz -C $W/llama; }
( get_prebuilt "$LLAMA_TAG" || { T=$(curl -fsSL "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=5" | python3 -c "import json,sys;print(next(r['tag_name'] for r in json.load(sys.stdin) if r['tag_name'].startswith('b')))"); get_prebuilt "$T"; } ) > $O/llama_dl.log 2>&1 &
PID_BIN=$!
( pip install -q -U "huggingface_hub[hf_xet]" gguf >/dev/null 2>&1
  hf download "$MODEL_REPO" "$MODEL_FILE" --local-dir $W/models || curl -fL -C - -o "$M" "https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE" ) > $O/model_dl.log 2>&1 &
PID_MODEL=$!

# ---- RAM bandwidth (STREAM-style triad, OpenMP), before the balloon exists
st bandwidth
command -v gcc >/dev/null || (apt-get update -qq && apt-get install -y -qq gcc >/dev/null 2>&1)
cat > /tmp/triad.c <<'C'
#include <stdio.h>
#include <stdlib.h>
#include <omp.h>
#define N 100000000L
int main(){ double *a=malloc(N*8),*b=malloc(N*8),*c=malloc(N*8); double best_t=1e9,best_c=1e9,s=3.0;
#pragma omp parallel for
 for(long i=0;i<N;i++){a[i]=1;b[i]=2;c[i]=0;}
 for(int k=0;k<8;k++){ double t=omp_get_wtime();
#pragma omp parallel for
  for(long i=0;i<N;i++) a[i]=b[i]+s*c[i];
  t=omp_get_wtime()-t; if(t<best_t)best_t=t;
  t=omp_get_wtime();
#pragma omp parallel for
  for(long i=0;i<N;i++) c[i]=a[i];
  t=omp_get_wtime()-t; if(t<best_c)best_c=t; }
 printf("threads=%d triad_GBps=%.1f copy_GBps=%.1f\n",omp_get_max_threads(),3.0*8*N/best_t/1e9,2.0*8*N/best_c/1e9); return 0;}
C
gcc -O3 -march=native -fopenmp /tmp/triad.c -o /tmp/triad 2>>$O/progress.log
for T in 1 10 16 $NPROC; do OMP_NUM_THREADS=$T OMP_PROC_BIND=spread taskset -c 0-$((NPROC-1)) /tmp/triad; done > $O/stream.txt 2>&1
TSK="0-$(( NPROC>16 ? 15 : NPROC-1 ))"
OMP_NUM_THREADS=10 taskset -c $TSK /tmp/triad | sed 's/^/pinned_0-15 /' >> $O/stream.txt 2>&1
cat $O/stream.txt | tee -a $O/progress.log

# ---- PCIe host->device bandwidth (pinned memory, torch)
python3 - > $O/pcie.txt 2>&1 <<'PY'
import torch, time
for d in range(torch.cuda.device_count()):
    x = torch.empty(1 << 30, dtype=torch.uint8).pin_memory(); y = torch.empty(1 << 30, dtype=torch.uint8, device=f"cuda:{d}")
    y.copy_(x, non_blocking=True); torch.cuda.synchronize(d); best = 9
    for _ in range(5):
        t = time.time(); y.copy_(x, non_blocking=True); torch.cuda.synchronize(d); best = min(best, time.time() - t)
    print(f"gpu{d} {torch.cuda.get_device_name(d)} H2D_GBps={1.073741824/best:.1f}")
    del x, y; torch.cuda.empty_cache()
PY
cat $O/pcie.txt >> $O/progress.log

wait $PID_BIN; SERVER=$(find $W/llama -name llama-server -type f | head -1); export LD_LIBRARY_PATH="$(dirname "$SERVER"):${LD_LIBRARY_PATH:-}"
log "llama-server $SERVER $("$SERVER" --version 2>&1 | head -2 | tr '\n' ' ')"
st downloading_model
wait $PID_MODEL; [ -s "$M" ] || { st model_download_failed; exit 1; }
log "model $(du -h $M | cut -f1)"

# ---- per-layer expert bytes from the GGUF
python3 - > $O/expert_bytes.json 2>>$O/progress.log <<PY
import json, re
from gguf import GGUFReader
r = GGUFReader("$M"); per = {}; tot = 0; exp = 0
for t in r.tensors:
    n = int(t.n_bytes); tot += n; m = re.match(r"blk\.(\d+)\.ffn_(up|down|gate)_exps", t.name)
    if m: per[int(m.group(1))] = per.get(int(m.group(1)), 0) + n; exp += n
print(json.dumps({"total_bytes": tot, "expert_bytes": exp, "n_layers": len(per), "per_layer": per}))
PY
LAYER_MIB=$(python3 -c "import json;d=json.load(open('$O/expert_bytes.json'));print(int(max(d['per_layer'].values())/2**20))" 2>/dev/null || echo 1730)
NL=$(python3 -c "import json;print(json.load(open('$O/expert_bytes.json'))['n_layers'])" 2>/dev/null || echo 36)
log "expert MiB per layer $LAYER_MIB, layers $NL"

# ---- RAM cap 64 GiB: try a child cgroup, else an mlocked balloon
st ram_cap
LIM=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo max)
MEMTOTAL=$(awk '/MemTotal/{print $2*1024}' /proc/meminfo)
CAP=$((64*1024*1024*1024)); CGROUP_OK=0; RUNPFX=""
if mkdir -p /sys/fs/cgroup/minipc 2>/dev/null && echo $CAP > /sys/fs/cgroup/minipc/memory.max 2>/dev/null && echo 0 > /sys/fs/cgroup/minipc/memory.swap.max 2>/dev/null; then
  CGROUP_OK=1; RUNPFX="cg"; echo "method=cgroup_v2_child memory.max=$CAP" > $O/ramcap.txt
else
  python3 -c "
lim='$LIM'.strip(); mt=$MEMTOTAL
L = mt if (lim=='max' or int(lim) > mt) else int(lim)
print(L)" > /tmp/effective_limit
  EFF=$(cat /tmp/effective_limit); BAL=$(( EFF - CAP ))
  echo "method=balloon cgroup_limit=$LIM memtotal=$MEMTOTAL effective_limit=$EFF balloon_bytes=$BAL" > $O/ramcap.txt
  if [ "$LIM" = "max" ]; then echo "WARNING: no container memory limit visible; balloon sized against host MemTotal" >> $O/ramcap.txt; fi
  if [ "$LIM" = "max" ]; then echo "no balloon: no container limit to size it against" >> $O/ramcap.txt; BAL=0; fi
  if [ $BAL -gt 0 ]; then
    nohup python3 - $BAL > $O/balloon.log 2>&1 <<'PY' &
import sys, mmap, ctypes, time
n = int(sys.argv[1]); m = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
for off in range(0, n, 4096): m[off] = 1
libc = ctypes.CDLL("libc.so.6", use_errno=True); rc = libc.mlockall(3)
print(f"balloon touched {n/2**30:.1f} GiB; mlockall rc={rc} errno={ctypes.get_errno()}", flush=True)
try: open("/proc/self/oom_score_adj", "w").write("-1000"); print("oom_score_adj -1000", flush=True)
except Exception as e: print("oom_score_adj not lowered:", e, flush=True)
while True: time.sleep(3600)
PY
    echo $! > $W/balloon.pid; sleep 5
    while ! grep -q touched $O/balloon.log 2>/dev/null; do sleep 5; kill -0 $(cat $W/balloon.pid) 2>/dev/null || break; done
    cat $O/balloon.log >> $O/ramcap.txt
  fi
fi
{ free -g; grep -E "MemAvailable|Mlocked|SwapTotal" /proc/meminfo; cat /sys/fs/cgroup/memory.current 2>/dev/null; } >> $O/ramcap.txt
cat $O/ramcap.txt >> $O/progress.log

# ---- server launcher. -ts 22,12 puts layers 0..23 on GPU0 and 24..35 (+output) on GPU1.
#      G0 = expert layers kept on GPU0 (the last G0 of 0..23), G1 = on GPU1 (the first G1 of 24..35); all others' experts -> CPU.
NGPU=$(nvidia-smi -L | wc -l); TS="-ts 22,12"; SPLIT=24
if [ "$NGPU" -lt 2 ]; then TS=""; SPLIT=$NL; T0MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1); CAP0=34304; [ $CAP0 -gt $((T0MIB-700)) ] && CAP0=$((T0MIB-700)); CAP1=999999; G0_START=${G0_START:-$(( (CAP0-10500)/LAYER_MIB ))}; G1_START=0; log "single-GPU fallback: whole 34 GB budget on GPU0 (cap $CAP0 MiB)"; fi
echo "ngpu=$NGPU ts='$TS' split=$SPLIT cap0=$CAP0 cap1=$CAP1" >> $O/sysinfo.txt
cpu_layers(){ local g0=$1 g1=$2 L=""; for i in $(seq 0 $((SPLIT-1-g0))); do L="$L|$i"; done; for i in $(seq $((SPLIT+g1)) $((NL-1))); do L="$L|$i"; done; echo "${L#|}"; }
start_server(){ local g0=$1 g1=$2; pkill -f llama-server; sleep 3; local CL=$(cpu_layers $g0 $g1)
  if [ "$NGPU" -lt 2 ]; then OTARGS=(--n-cpu-moe $((NL-g0))); else OTARGS=(-ot "blk\\.($CL)\\.ffn_(up|down|gate)_exps=CPU"); fi; echo "${OTARGS[*]}" > $W/ot.txt
  local CMD=(taskset -c $TSK "$SERVER" -m "$M" --jinja -c $CTX -ngl 99 $TS "${OTARGS[@]}" -np 1 -t 10 -tb 16 -b 2048 -ub 2048
             --host 0.0.0.0 --port $PORT --metrics -to 600)
  if [ $CGROUP_OK = 1 ]; then ( echo $BASHPID > /sys/fs/cgroup/minipc/cgroup.procs; exec "${CMD[@]}" ) > $W/llama_server.log 2>&1 &
  else "${CMD[@]}" > $W/llama_server.log 2>&1 & fi
  echo $! > $W/llama_server.pid
  for i in $(seq 1 120); do curl -fs localhost:$PORT/health 2>/dev/null | grep -q ok && return 0; kill -0 $(cat $W/llama_server.pid) 2>/dev/null || return 1; sleep 5; done; return 1; }
probe(){ python3 - "$@" <<'PY'
import json, sys, urllib.request, subprocess, random
def post(path, body):
    r = urllib.request.Request("http://127.0.0.1:8000" + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=900))
random.seed(7); filler = " ".join(f"row{i}: {random.randint(100,999)}" for i in range(700))
post("/v1/chat/completions", {"messages": [{"role": "user", "content": "Sum nothing, just say ok. " + filler}], "max_tokens": 32, "cache_prompt": False})
gen = []
for k in range(2):
    j = post("/v1/chat/completions", {"messages": [{"role": "user", "content": f"Write a 400-word story about a lighthouse keeper (variant {k})."}],
             "max_tokens": 300, "cache_prompt": False, "chat_template_kwargs": {"reasoning_effort": "low"}})
    gen.append(j["timings"]["predicted_per_second"])
mem = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.split()
print(json.dumps({"g0": int(sys.argv[1]), "g1": int(sys.argv[2]), "mem_mib": [int(x) for x in mem], "gen_tok_s": gen}))
PY
}

# ---- tune expert plaproduct against the VRAM caps (measured with KV cache + compute buffers allocated)
st tuning
G0=${G0_START:-9}; G1=${G1_START:-4}; BEST=""; : > $O/tune.jsonl
for it in 1 2 3 4 5 6 7; do
  if start_server $G0 $G1; then
    R=$(probe $G0 $G1); echo "$R" >> $O/tune.jsonl; log "tune $R"
    read M0 M1 <<< $(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);m=d['mem_mib']+[0];print(m[0],m[1])")
  else log "tune G0=$G0 G1=$G1 failed to load"; tail -5 $W/llama_server.log >> $O/progress.log; M0=$((CAP0+1)); M1=$((CAP1+1)); fi
  if [ $M0 -le $CAP0 ] && [ $M1 -le $CAP1 ]; then
    BEST="$G0 $G1"; N0=$(( (CAP0-M0)/LAYER_MIB )); N1=$(( (CAP1-M1)/LAYER_MIB ))
    [ $NGPU -lt 2 ] && N1=0; [ $N0 -eq 0 ] && [ $N1 -eq 0 ] && break
    TRIED=$(cat $O/tune.jsonl); G0=$((G0+N0)); G1=$((G1+N1))
  else
    [ $M0 -gt $CAP0 ] && G0=$((G0 - 1 - (M0-CAP0)/LAYER_MIB)); [ $M1 -gt $CAP1 ] && G1=$((G1 - 1 - (M1-CAP1)/LAYER_MIB))
    [ -n "$BEST" ] && { set -- $BEST; [ $G0 -lt $1 ] && G0=$1; [ $G1 -lt $2 ] && G1=$2; [ "$G0 $G1" = "$BEST" ] && break; }
    [ $G0 -lt 0 ] && G0=0; [ $G1 -lt 0 ] && G1=0
  fi
done
[ -z "$BEST" ] && { st tuning_failed; exit 1; }
set -- $BEST; G0=$1; G1=$2
start_server $G0 $G1 || { st final_start_failed; exit 1; }
CPU_LAYERS=$(cpu_layers $G0 $G1)
python3 -c "
import json; d=json.load(open('$O/expert_bytes.json')); cl=[int(x) for x in '$CPU_LAYERS'.split('|') if x]
cpu=sum(d['per_layer'][str(i)] if str(i) in d['per_layer'] else d['per_layer'][i] for i in cl)
print(json.dumps({'g0':$G0,'g1':$G1,'cpu_expert_layers':cl,'cpu_expert_bytes':cpu,'cpu_active_bytes_per_token':cpu*4/128,
 'override':open('$W/ot.txt').read().strip(),'ngpu':$NGPU,'flags':'-c $CTX -ngl 99 $TS -np 1 -t 10 -tb 16 -b 2048 -ub 2048 -to 600 --jinja, taskset -c $TSK'}))" > $O/final_config.json
grep -E "model buffer size|KV buffer size|compute buffer size|offloaded" $W/llama_server.log > $O/buffers.txt
cat $O/final_config.json >> $O/progress.log

# ---- benchmarks: decode-only + long context (synthetic ledger, no prompt cache)
st benchmarking
python3 - > $O/bench.json 2>>$O/progress.log <<'PY'
import json, random, statistics, time, urllib.request, subprocess
def post(path, body, to=2400):
    r = urllib.request.Request("http://127.0.0.1:8000" + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=to))
def ntok(s): return len(post("/tokenize", {"content": s})["tokens"])
out = {"decode": [], "long": []}
for k in range(3):
    j = post("/v1/chat/completions", {"messages": [{"role": "user", "content": f"Explain in about 500 words how a refrigerator works (take {k})."}],
             "max_tokens": 512, "cache_prompt": False, "chat_template_kwargs": {"reasoning_effort": "low"}})
    out["decode"].append(j["timings"])
regions = ["North-%d" % i for i in range(1, 9)] + ["South-%d" % i for i in range(1, 9)]
skus = ["SKU-A%02d" % i for i in range(1, 13)]
for target, seed in ((8000, 11), (20000, 22), (30000, 33)):
    rnd = random.Random(seed); rows = []; truth = 0
    def line(i):
        r, s, q = rnd.choice(regions), rnd.choice(skus), rnd.randint(1, 500)
        return r, s, q, f"2025-{rnd.randint(1,12):02d}-{rnd.randint(1,28):02d} | order {seed}{i:06d} | {r} | {s} | qty {q} | price {rnd.randint(200,900)}.{rnd.randint(0,99):02d}"
    i = 0; text = []
    per = max(1, ntok("\n".join(line(k)[3] for k in range(50))) / 50); rnd = random.Random(seed)
    n_rows = int((target - 200) / per)
    for i in range(n_rows):
        r, s, q, l = line(i); text.append(l)
        if r == "North-3" and s == "SKU-A07": truth += q
    q = ("Below is a synthetic order ledger (illustrative data). Task: report the total qty of SKU-A07 orders in region North-3, "
         "and name the region with the most order lines. Answer briefly.\n\n" + "\n".join(text))
    n = ntok(q); t = time.time()
    j = post("/v1/chat/completions", {"messages": [{"role": "user", "content": q}], "max_tokens": 1024, "cache_prompt": False,
                                       "chat_template_kwargs": {"reasoning_effort": "low"}})
    wall = time.time() - t; tm = j["timings"]; ans = j["choices"][0]["message"].get("content", "")
    out["long"].append({"target": target, "prompt_tokens": tm["prompt_n"], "pp_tok_s": tm["prompt_per_second"], "ttft_s": tm["prompt_ms"] / 1000,
                        "gen_tokens": tm["predicted_n"], "gen_tok_s": tm["predicted_per_second"], "wall_s": round(wall, 1),
                        "truth_qty": truth, "answer": ans[:400], "qty_correct": str(truth) in ans.replace(",", "")})
mem = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.split()
out["mem_mib_after"] = [int(x) for x in mem]
out["decode_median_tok_s"] = statistics.median(d["predicted_per_second"] for d in out["decode"])
print(json.dumps(out, indent=1))
PY
cat $O/bench.json >> $O/progress.log
cp $W/llama_server.log $O/llama_server_bench.log
# ---- background sampler during the tough pack
nohup bash -c "while true; do echo \"\$(date -u +%H:%M:%S),\$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr '\n' ','),\$(cat /sys/fs/cgroup/memory.current 2>/dev/null),\$(awk '/MemAvailable/{print \$2}' /proc/meminfo)\" >> $O/samples.csv; cp $W/llama_server.log $O/llama_server.log; sleep 15; done" >/dev/null 2>&1 &
st ready
