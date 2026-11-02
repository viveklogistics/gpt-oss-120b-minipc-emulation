# gpt-oss-120b on a 64 GB mini PC + 34 GB eGPUs: agentic test kit and emulation results

This kit checks whether **gpt-oss-120b** (MXFP4 GGUF, served by llama.cpp `llama-server` with tool calling) can do
multi-step analytics work by writing and running its own Python: data cleaning, forecasting, MILP planning, truck
loading, infeasibility handling, what-if analysis and everyday Excel tasks. It also contains a script that **emulates a
consumer mini PC** (64 GB DDR4, i7-13620H class, two USB4 eGPUs with 22 GB + 12 GB) on one rented GPU.

**Results: see [`RESULTS.md`](RESULTS.md).** The H100 reference report is in `results/h100_reference/H100_REPORT.md`.

> **All data in this kit is ILLUSTRATIVE SYNTHETIC DATA** for a made-up supply chain, generated from fixed seeds.
> It contains no real company, plant, depot or customer data.
>
> **Renaming note:** entity and column names in the synthetic data (the intermediate material, production stages,
> product grades) were made generic for publication after the published runs. Numbers, constraints and checkers are
> unchanged, and the regenerated reference answers are identical. The prompt wording differs slightly, so a rerun may
> not match the published verdicts exactly.

## Layout

| Folder | Contents |
|---|---|
| `original_pack/` | 4-test starter pack T2-T5 (data generator, reference solutions, checkers, harness, `run_all.py`) |
| `tough_pack/` | H1-H9 supply-chain tests, Excel round E1-E8, guarded mode (`guardrails.py`), mock server for offline dry runs. See `tough_pack/README.md` |
| `emulation/` | `run_emulation.sh` (end-to-end RunPod emulation run), `estimate.py` (mini-PC speed estimates from the measured numbers) |
| `pod/` | `runpod_ctl.py` (create / status / terminate / list RunPod pods via the REST API, with a local auto-terminate watchdog), `emulation_setup.sh` (runs on the pod: llama.cpp, GGUF download, STREAM, PCIe test, RAM balloon, VRAM tuning, benchmarks, llama-server), `pod_setup.sh` + `pod_pipeline.sh` (plain full-GPU run, as used for the H100 reference) |
| `results/minipc_emulation/` | Guarded and baseline scoresheets (`.md`, `.xlsx`), run metadata, server config and benchmark files |
| `results/h100_reference/` | H100 report, scoresheets and baseline-vs-guarded comparison |

Raw model transcripts and server logs are not included.

## Scoring rules

* The model only gets tools (`python_exec` in a sandbox, file read/list, `submit_answer`). Every checker re-validates
  the model's saved files or answer against a hidden reference that the model never sees.
* **A number counts only if the model's own code printed it.** A correct number that appears only in prose is a fail.
* Verdicts are `pass`, `partial` or `fail`, each with a written reason. Tool calls, tool errors, self-corrections,
  wall time and llama.cpp `timings` (prompt and generation tok/s) are logged per test.
* Tough pack: up to 40 model steps per test, 8,192 max tokens per turn, reasoning effort `medium`.
* **Guarded mode** (`--mode guarded`): extra system rules (check data quality first, flag prompt-vs-data conflicts,
  state assumptions on vague goals) and three helper tools: `data_quality`, `check_prompt_vs_data`, `forecast_blend`.

## Quick start (offline, no GPU)

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# LibreOffice is needed for the Excel checks (headless recalculation), e.g. apt-get install libreoffice-calc

cd original_pack && python tests/gen_data.py && python tests/reference.py && python tests/selftest_checkers.py && cd ..
cd tough_pack && python gen_data.py && python reference.py          # reference.py takes about 20 s
python selftest_excel.py                                            # Excel checker self-test
# mock dry run: the mock server replays the oracle (or deliberately wrong) solutions through the real harness
python mock/mock_server.py 8765 &  MOCK_WRONG=1 python mock/mock_server.py 8766 &
python run_tough.py --base-url http://127.0.0.1:8765/v1 --out results/dryrun_mock_correct      # expect 17/0/0
python run_tough.py --base-url http://127.0.0.1:8766/v1 --tests H1,H2,H3,H4,H5,H6,H7,H8,H9 --out results/dryrun_mock_wrong   # expect 0/3/6
python selftest_tough.py
python run_tough.py --mode guarded --base-url http://127.0.0.1:8765/v1 --out results/dryrun_guarded_mock   # expect 17/0/0
kill %1 %2
cd ..
```

## Run against any model

Any OpenAI-compatible endpoint with tool calling works (llama.cpp `llama-server --jinja` was used):

```bash
python original_pack/run_all.py --base-url http://HOST:8000/v1 --label "my run"
python tough_pack/run_tough.py --base-url http://HOST:8000/v1 --label "my run"            # writes scoresheet.xlsx and .md
python tough_pack/run_tough.py --mode guarded --base-url http://HOST:8000/v1 --label "my run, guarded"
python tough_pack/run_tough.py --rescore tough_pack/results/<run>     # re-check saved transcripts, no model calls
```

For slow hardware, set `WALL_SCALE` (multiplies tool/wall time limits, e.g. `2.5`) and `LLM_TIMEOUT_S` (e.g. `600`).

## Rerun the mini-PC emulation on RunPod (~2 h, ~$3.50 at $1.69/hr)

```bash
export RUNPOD_API_KEY=...            # set it in your environment only; never commit or print it
pip install -r requirements.txt      # plus LibreOffice for the Excel checks
bash emulation/run_emulation.sh      # optional env: MAXPRICE=2.65 BUDGET=3.8 HOURS=2.2 OUT=results/my_emulation
python pod/runpod_ctl.py list        # afterwards: confirm no pod is left running
```

What it does: tries a list of single 48 GB+ cards until one is available; refuses pods above `MAXPRICE` or with less
than 58 GB RAM; the pod downloads llama.cpp b12024 and the 63 GB GGUF, measures STREAM and PCIe bandwidth, inflates a RAM
balloon so ~64 GB is left, picks the largest `--n-cpu-moe` that keeps VRAM under 34,304 MiB, benchmarks decode and
8k/20k/30k-token prompts, then serves the model. Your machine runs the guarded pack, then the baseline pack, inside the
budget, writes results to `results/my_emulation`, prints the mini-PC estimates (`emulation/estimate.py`), and
**terminates the pod on any exit** (including Ctrl-C). Check `runpod_ctl.py list` anyway.

## Running it on the real mini PC (untested starting point)

```bash
llama-server -m gpt-oss-120b-MXFP4.gguf --jinja -c 65536 -ngl 99 -ts 22,12 --n-cpu-moe 19 \
  -np 1 -t 10 -tb 16 -b 2048 -ub 2048 -to 600
```

* Start with `--n-cpu-moe 19` and lower it until a GPU runs out of memory; keep ~1 GB of headroom on each card.
* Prompt processing over USB4 is the expected bottleneck. Try `--no-op-offload` and a larger `-ub` and compare.
* Use long client timeouts (`LLM_TIMEOUT_S=600`, `WALL_SCALE` of 4-8).

## Licence

MIT (see `LICENSE`).
