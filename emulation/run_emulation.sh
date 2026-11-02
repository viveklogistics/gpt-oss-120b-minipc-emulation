#!/bin/bash
# Emulate a consumer mini PC (64 GB DDR4, 10C/16T laptop CPU) + 34 GB of eGPU VRAM (22 GB + 12 GB) on ONE rented GPU,
# then run the tough pack (guarded first, then baseline). The pod is terminated on any exit.
# Run from the kit root:  export RUNPOD_API_KEY=...  (environment only)  &&  bash emulation/run_emulation.sh
# Env: MAXPRICE (USD/hr cap, default 2.65), BUDGET (USD, default 3.8), HOURS (hard pod lifetime, default 2.2), ROUNDS (retry rounds).
cd "$(dirname "$0")/.."; PY=${PY:-python}; MAXPRICE=${MAXPRICE:-2.65}; BUDGET=${BUDGET:-3.8}; HW=${HOURS:-2.2}; ROUNDS=${ROUNDS:-150}
R=${OUT:-results/my_emulation}; mkdir -p $R; created=""
# Single cards with >= 48 GB, in the order tried. The setup script caps usable VRAM at 34 GB (34,304 MiB) via --n-cpu-moe.
# If a 2-GPU pod is used instead, emulation_setup.sh switches to -ts 22,12 with per-GPU caps of 22,016 / 11,776 MiB.
CARDS=("NVIDIA RTX PRO 6000 Blackwell Workstation Edition|COMMUNITY" "NVIDIA RTX A6000|COMMUNITY" "NVIDIA A40|COMMUNITY" "NVIDIA L40S|COMMUNITY"
       "NVIDIA RTX 6000 Ada Generation|COMMUNITY" "NVIDIA A100 80GB PCIe|COMMUNITY" "NVIDIA RTX PRO 6000 Blackwell Server Edition|SECURE" "NVIDIA H100 PCIe|COMMUNITY")
for round in $(seq 1 $ROUNDS); do
 for spec in "${CARDS[@]}"; do
  IFS='|' read G C <<< "$spec"
  if $PY pod/runpod_ctl.py up --hours $HW --gpus "$G" --cloud $C --setup emulation_setup.sh --extra-port 8002/http \
       --name minipc-emulation --no-wait > $R/up.log 2>&1; then created=1; break 2; fi
 done
 echo "round $round: none available $(date +%H:%M:%S)"; sleep 20
done
[ -z "$created" ] && { echo "NO_POD_CREATED"; $PY pod/runpod_ctl.py list; exit 2; }
T0=$(date +%s); POD=$(cat pod/.pod_id); S=https://$POD-8002.proxy.runpod.net   # 8002 = read-only results server on the pod
fetch_all(){ mkdir -p $R/pod; for f in status.txt progress.log sysinfo.txt stream.txt pcie.txt ramcap.txt balloon.log expert_bytes.json tune.jsonl final_config.json buffers.txt bench.json samples.csv llama_server.log llama_server_bench.log llama_dl.log; do
  curl -fs -m 60 $S/$f -o $R/pod/$f.tmp && mv $R/pod/$f.tmp $R/pod/$f; done; rm -f $R/pod/*.tmp; }
cleanup(){ fetch_all; echo "POD_SECONDS $(( $(date +%s) - T0 ))"; $PY pod/runpod_ctl.py terminate $POD; sleep 5
           echo "LIST_AFTER:"; $PY pod/runpod_ctl.py list; echo "LIST_END"; }
trap cleanup EXIT
PRICE=$(grep -o 'costPerHr=[0-9.]*' $R/up.log | cut -d= -f2); echo "CREATED $POD gpu=$G cloud=$C price=$PRICE/hr"
python3 -c "import sys; sys.exit(0 if float('${PRICE:-99}') <= $MAXPRICE else 1)" || { echo "PRICE $PRICE > $MAXPRICE/hr"; exit 3; }
$PY pod/runpod_ctl.py status $POD > $R/pod_status.json 2>&1
MEMGB=$(python3 -c "import json;print(json.load(open('$R/pod_status.json')).get('memoryInGb') or 0)" 2>/dev/null || echo 0)
python3 -c "import sys; sys.exit(0 if float('$MEMGB') >= 58 else 1)" || { echo "POD RAM ${MEMGB} GB too small"; exit 6; }
HMAX=$(python3 -c "print(round(min($HW, $BUDGET/float('$PRICE') - 0.05),2))"); echo "budget hours $HMAX"
left(){ python3 -c "print(round($HMAX*60 - ($(date +%s)-$T0)/60 - ${1:-0}, 1))"; }
last=""
while true; do   # setup: llama.cpp + 63 GB GGUF download, STREAM, PCIe test, RAM balloon, VRAM tuning, benchmarks
  st=$(curl -fs -m 20 $S/status.txt 2>/dev/null); [ "$st" != "$last" ] && { echo "[$(date +%H:%M:%S)] pod status: ${st:-<no response>}"; last="$st"; }
  case "$st" in ready) break;; *failed*) fetch_all; tail -30 $R/pod/progress.log; exit 4;; esac
  [ $(( $(date +%s) - T0 )) -gt 6000 ] && { echo "SETUP TIMEOUT"; fetch_all; tail -30 $R/pod/progress.log; exit 5; }
  sleep 30
done
fetch_all; cat $R/pod/final_config.json; echo
GEN=$(python3 -c "import json;print(json.load(open('$R/pod/bench.json'))['decode_median_tok_s'])")
# Scale tool/wall timeouts so a slower decode is not penalised (176 tok/s = the H100 reference decode speed)
export WALL_SCALE=$(python3 -c "print(round(min(6,max(1,176/$GEN)),2))") LLM_TIMEOUT_S=600; echo "WALL_SCALE $WALL_SCALE"
URL=https://$POD-8000.proxy.runpod.net/v1; LBL="gpt-oss-120b MXFP4, mini-PC emulation ($(echo $G|sed 's/NVIDIA //'), VRAM capped to 34 GB, RAM <=64 GB, -t 10)"
TESTS=${TESTS:-H1,H2,H3,H4,H5,H6,H7,H8,H9,E1,E2,E3,E4,E5,E6,E7,E8}
DL=$(python3 -c "print(round(($(left 8))/2,1))"); echo "GUARDED start, deadline $DL min"
$PY tough_pack/run_tough.py --base-url $URL --mode guarded --label "$LBL GUARDED" --tests $TESTS --deadline-min $DL --out $R/guarded
fetch_all; DL=$(left 8); echo "BASELINE start, deadline $DL min"
$PY tough_pack/run_tough.py --base-url $URL --mode baseline --label "$LBL baseline" --tests $TESTS --deadline-min $DL --out $R/baseline
echo "ALL_TESTS_DONE"; $PY emulation/estimate.py $R/pod
