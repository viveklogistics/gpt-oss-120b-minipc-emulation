# gpt-oss-120b on a 64 GB mini PC + 34 GB of USB4 eGPUs: an emulated test (tool calling, ML / OR / Excel)

*Run date: 2 November 2026. All task data is **illustrative synthetic data** for a made-up supply chain, generated from
fixed seeds. No real company data was used. Everything needed to rerun this is in this kit (MIT licence).*

## TL;DR

- **Question:** can a consumer mini PC with **64 GB of DDR4** and **two eGPUs over USB4 (22 GB + 12 GB = 34 GB VRAM)**
  run **gpt-oss-120b** (MXFP4, llama.cpp) well enough to do multi-step agentic analytics work?
- **How:** we did not have the box set up yet, so we **emulated** its memory limits on one rented GPU (RTX PRO 6000,
  96 GB) with VRAM capped to 34 GB and host RAM held to about 64 GB, then ran a 17-test agentic pack.
- **Quality:** with the same model and quant, the emulated setup scored **12 pass / 3 partial / 2 fail** in guarded mode,
  against **10 / 4 / 3** for the same pack on a full H100 earlier. Quality does not depend on where the weights sit;
  the difference is within run-to-run noise.
- **Speed measured on the emulator:** about **65-70 tok/s** generation, **1,700-2,000 tok/s** prompt processing.
- **Speed ESTIMATED for the real mini PC (not measured):** about **38-48 tok/s** generation and about
  **180-230 tok/s** prompt processing. The USB4 link, not RAM, is the expected bottleneck: a 30k-token prompt would take
  roughly **2-3 minutes** before the first token.
- **Cost:** about **$3.50** of GPU time (2.07 h at $1.69/hr).

## 1. The target machine and how it was emulated

| Item | Real target (consumer mini PC) | What the emulation pod did |
|---|---|---|
| Machine | Geekom GT13 Pro-class mini PC, Intel i7-13620H (10 cores / 16 threads) | AMD EPYC 9374F host; llama-server pinned with `taskset -c 0-15`, `-t 10 -tb 16` |
| Host RAM | 64 GB DDR4-3200 SO-DIMM, dual channel, **~51 GB/s theoretical** (typically ~40-45 GB/s in STREAM) | The pod had 227 GB. A **balloon** process allocated and touched 147.4 GiB, leaving **about 64 GiB** for the model mmap, page cache and server (no swap on the pod, so the balloon stayed resident) |
| GPUs | Two eGPUs over USB4: **22 GB + 12 GB = 34 GB** | **One** RTX PRO 6000 Blackwell (96 GB) with usable VRAM capped at **34,304 MiB**. No 2-GPU pods were available during the session, so this is **not a real 22 + 12 split** |
| VRAM used | <= 34 GB | Peak **33,268 MiB (32.5 GiB)** including the 64k KV cache and compute buffers, sampled every 15 s for the whole run |
| Expert placement | MoE experts that do not fit go to CPU RAM | `--n-cpu-moe 19`: expert weights of layers 0-18 (32.2 GB) stay in RAM, layers 19-35 on the GPU. Tuning: 14 GPU expert layers = 28.4 GB VRAM and 52-63 tok/s; 17 = 33.3 GB and ~70 tok/s (largest that fits) |
| Host-to-GPU link | USB4 / TB4 PCIe tunnel, ~3-3.8 GB/s effective | PCIe 5.0 x16, measured **57.6 GB/s** pinned host-to-device |
| RAM bandwidth (STREAM-style triad) | ~51 GB/s theoretical | **75.3 GB/s** pinned to CPUs 0-15 with 10 threads (how the server ran). Unpinned: 151 GB/s (10 threads) |

**Server:** llama.cpp **b12024** (prebuilt CUDA 12.8), model `ggml-org/gpt-oss-120b-GGUF` / `gpt-oss-120b-MXFP4.gguf` (~63 GB):

```
taskset -c 0-15 llama-server -m gpt-oss-120b-MXFP4.gguf --jinja -c 65536 -ngl 99 --n-cpu-moe 19 \
  -np 1 -t 10 -tb 16 -b 2048 -ub 2048 -to 600
```

Client: reasoning effort `medium`, max 40 steps, 8,192 max tokens per turn, temperature 0, 600 s LLM timeout. Tool time limits were scaled by 176 / measured
tok/s (about 2.5x) so the slower decode was not penalised.

## 2. Tough pack results (17 tests) vs the H100 reference

The pack: H1-H9 are supply-chain analytics tasks on a synthetic network (data cleaning, hierarchical forecasting,
production/transport MILPs, truck loading, an infeasibility trap, a what-if with shadow prices, a chained task, a vague
request, and a prompt-vs-data conflict). E1-E8 are everyday Excel tasks checked by recalculating the saved `.xlsx` in
LibreOffice. The model only gets a sandboxed `python_exec`, file tools and `submit_answer`; **a number counts only if
the model's own code printed it.** "Guarded" mode adds system rules and three helper tools (see `tough_pack/guardrails.py`).

| Test | H100 baseline | Emulated baseline | H100 guarded | Emulated guarded |
|---|---|---|---|---|
| H1 Clean 26,935 raw invoices | fail | fail | partial | partial |
| H2 300-district forecast + reconciliation | partial | fail* | pass | pass |
| H3 3-month production / transfer / inventory MILP | pass | pass | pass | pass |
| H4 Club 200 invoices onto trucks | partial | fail | partial | fail* |
| H5 Infeasibility trap | pass | fail | fail | pass |
| H6 Outage what-if + shadow prices | partial | fail* | partial | partial |
| H7 Chained forecast -> plan -> trucks | fail | pass | fail | fail* |
| H8 Vague goal ("cut freight cost") | fail | not run | pass | pass |
| H9 Prompt contradicts the data | fail | not run | pass | pass |
| E1-E8 Excel round | 6 pass / 1 partial / 1 fail | not run | 6 pass / 1 partial / 1 fail | 7 pass / 1 partial |
| **Totals** | **8 / 4 / 5** (17 tests) | **2 / 0 / 5** (7 tests only) | **10 / 4 / 3** | **12 / 3 / 2** |
| Wall time | 19.2 min | 57.1 min (7 tests) | 23.8 min | 42.0 min |

Totals are pass / partial / fail. On the **same 7 tests (H1-H7)** the H100 baseline scored **2 / 3 / 2**.

\* The turn ended with a llama.cpp error, `The model produced output that does not match the expected peg-native
format`. This is a chat-template / tool-call parser issue in this llama.cpp build, **not** an effect of the memory
limits. It hit baseline H2 and H6 and guarded H4 and H7 (and E3/E6, which still passed because the files were already
saved). A newer build or a different template may change those verdicts.

The **baseline run is incomplete**: guarded ran first, and the baseline stopped after H7 when the pod reached its
budget deadline. Do not read the baseline column as a full score.

## 3. Long-context runs (synthetic order ledger, 64k context window)

The prompt is a synthetic ledger; the question asks for the total quantity of one SKU in one region (exact answer known).

| Prompt tokens | Prompt processing (pod) | Time to first token (pod) | Generation (pod) | Correct? |
|---|---|---|---|---|
| 7,888 | 1,684 tok/s | 4.7 s | 68.5 tok/s | yes (289) |
| 19,916 | 1,928 tok/s | 10.3 s | 64.8 tok/s | yes (134) |
| 29,898 | 2,036 tok/s | 14.7 s | 63.6 tok/s | **no** (answered 0, truth 822) |

One sample per length. The 30k miss is a warning sign for long-context retrieval, but one sample is not a measurement
of an error rate. Short-prompt generation (median of 3 x 512 tokens): **70.2 tok/s**.

## 4. ESTIMATES for the real mini PC (these are estimates, not measurements)

| Prompt tokens | Prompt processing (EST.) | Time to first token (EST.) | Generation (EST.) |
|---|---|---|---|
| short prompt | - | - | **40-48 tok/s** |
| 7,888 | 180-224 tok/s | 35-44 s | 39.7-47.7 tok/s |
| 19,916 | 182-228 tok/s | 87-109 s | 38.4-45.9 tok/s |
| 29,898 | 183-229 tok/s | 130-163 s | 38.0-45.2 tok/s |

How they were derived (`emulation/estimate.py`):

- **Generation:** each token reads the active experts of the 19 CPU-resident layers from RAM: 1.007 GB/token (4 of 128
  experts x 19 layers, sizes read from the GGUF). We add the extra RAM-read time going from the pod's 75.3 GB/s to
  42-51 GB/s: 14.2 ms/token becomes about 20.6-24.9 ms (**~40-48 tok/s**). This is an **upper bound**: it ignores the
  laptop CPU's lower compute, power limits and thermals, and any 2-GPU split overhead.
- **Prompt processing:** with `-ub 2048`, llama.cpp copies the CPU-resident expert weights (32.2 GB) to the GPU for
  every 2,048-token micro-batch. That takes ~0.56 s over PCIe 5.0 but ~8.5-10.7 s over a 3.0-3.8 GB/s USB4 tunnel, so
  prompt speed drops to **~180-230 tok/s**. Worth testing on the real box: `--no-op-offload` (compute CPU experts on
  the CPU instead of copying) or a larger `-ub`; either could move this by roughly 2x in either direction.
- **Agentic wall time:** most turns carry 2-15k tokens of prompt, so expect roughly **4-8x the emulator's wall time**
  for the tough pack. Scores should be the same (same model, quant and template), with more timeout risk on the long
  MILP tasks. Set generous client timeouts (~10 min).

## 5. Caveats

- **Single card, not a real 22 + 12 GB split.** Layer splitting across two GPUs (`-ts 22,12`) and USB4 latency were not
  exercised. The setup script supports a 2-GPU pod if you can get one.
- **RAM bandwidth was higher than the target.** Pinned STREAM triad was 75 GB/s vs ~40-51 GB/s on DDR4-3200, and the
  link was PCIe 5.0 instead of USB4. That is why the speeds above are adjusted by estimate.
- **The RAM cap is a balloon, not a cgroup limit.** `mlockall` failed, but the pod has no swap, so the balloon pages
  stayed resident; the container sat at its memory limit leaving ~64 GiB.
- **One run per mode.** Differences of about +/-2 tests between runs are within noise.
- **Parser errors** in llama.cpp b12024 affected several verdicts (section 2).
- **The baseline run is partial** (7 of 17 tests).
- Domain labels in the synthetic data were made generic for publication after these runs (for example the intermediate
  material and the production stages were renamed). Numbers, constraints and checkers are unchanged and the regenerated
  reference answers are identical, but prompt wording differs slightly, so a rerun may not match verdict for verdict.

## 6. Cost

- Emulation pod: 1x RTX PRO 6000 Blackwell Workstation (RunPod Community Cloud), **$1.69/hr**, 7,445 s billed
  (2.07 h) = **about $3.50**. Availability probes added a few cents at most. The pod was terminated and the pod list was
  empty afterwards.
- The earlier H100 NVL reference runs are documented in [`h100-baseline/RESULTS_H100.md`](h100-baseline/RESULTS_H100.md).

## 7. Files

| Path | What |
|---|---|
| `results/minipc_emulation/guarded/`, `baseline/` | Scoresheets (`.md` and `.xlsx`) and run metadata |
| `results/minipc_emulation/server_and_bench/` | `bench.json` (decode + long context), `final_config.json`, `stream.txt`, `pcie.txt`, `tune.jsonl`, `buffers.txt`, `samples.csv` (VRAM / RAM every 15 s), `ramcap.txt`, `expert_bytes.json`, `sysinfo.txt` |
| `h100-baseline/` | H100 NVL baseline report, scoresheets and comparison |
| `emulation/`, `pod/`, `tough_pack/`, `original_pack/` | Everything needed to rerun; see `README.md` |
