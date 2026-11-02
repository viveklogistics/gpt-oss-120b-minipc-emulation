#!/bin/bash
# Retry pod creation (A100 80GB first, then H100 under $3/hr), wait for llama-server, run the packs, always terminate.
# Run from the kit root with RUNPOD_API_KEY exported (never written to a file). Env: HOURS (default 0.8), BUDGET (USD, default 3),
# TESTS (default all H and E tests), OUT (results folder), ROUNDS (retry rounds, 1 per minute),
# MODE (baseline or guarded, default baseline), CTX (llama-server context; default 32768; the pod falls back to 65536 if a larger one does not fit).
# Guarded rerun used: MODE=guarded CTX=131072 HOURS=1.1 OUT=tough_pack/results/guarded bash pod/pod_pipeline.sh
cd "$(dirname "$0")/.."; PY=${PY:-python}; ROUNDS=${ROUNDS:-30}; HOURS=${HOURS:-0.8}; created=""
for round in $(seq 1 $ROUNDS); do
 for spec in "NVIDIA A100-SXM4-80GB,NVIDIA A100 80GB PCIe|SECURE" "NVIDIA A100-SXM4-80GB,NVIDIA A100 80GB PCIe|COMMUNITY" "NVIDIA H100 NVL,NVIDIA H100 PCIe|SECURE" "NVIDIA H100 NVL,NVIDIA H100 80GB HBM3,NVIDIA H100 PCIe|COMMUNITY"; do
  IFS='|' read G C <<< "$spec"
  if $PY pod/runpod_ctl.py up --hours $HOURS --gpus "$G" --cloud $C ${CTX:+--ctx $CTX} --name gptoss120b-tough --no-wait > up.log 2>&1; then created=1; break 2; fi
 done
 echo "round $round: none available $(date +%H:%M:%S)"; sleep 60
done
[ -z "$created" ] && { echo "NO_POD_CREATED"; $PY pod/runpod_ctl.py list; exit 2; }
T0=$(date +%s); POD=$(cat pod/.pod_id); echo "CREATED $POD cloud=$C"; grep -E "created pod|armed" up.log
PRICE=$(grep -o 'costPerHr=[0-9.]*' up.log | cut -d= -f2)
if ! python3 -c "import sys; sys.exit(0 if float('${PRICE:-99}') <= 3.0 else 1)"; then
  echo "PRICE $PRICE > 3/hr, terminating"; $PY pod/runpod_ctl.py terminate $POD; $PY pod/runpod_ctl.py list; exit 3; fi
HMAX=$(python3 -c "print(min($HOURS, float('${BUDGET:-3}')/float('$PRICE') - 0.06))")
$PY -c "import sys; sys.path.insert(0,'pod'); import runpod_ctl as r; sys.exit(0 if r.wait_ready('$POD', 30) else 1)" || { echo "NOT READY"; $PY pod/runpod_ctl.py terminate $POD; $PY pod/runpod_ctl.py list; exit 4; }
DL=$(python3 -c "print(round($HMAX*60 - ($(date +%s)-$T0)/60 - 4, 1))"); echo "READY, test deadline $DL min"
$PY tough_pack/run_tough.py --mode ${MODE:-baseline} --base-url https://$POD-8000.proxy.runpod.net/v1 --label "gpt-oss-120b MXFP4 llama.cpp ($(echo $G | cut -d, -f1), $C)" \
   --tests ${TESTS:-H1,H2,H3,H4,H5,H6,H7,H8,H9,E1,E2,E3,E4,E5,E6,E7,E8} --deadline-min $DL --terminate-pod $POD --out ${OUT:-tough_pack/results/pod_run}
$PY pod/runpod_ctl.py terminate $POD; echo "LIST_AFTER:"; $PY pod/runpod_ctl.py list; echo "LIST_END"
