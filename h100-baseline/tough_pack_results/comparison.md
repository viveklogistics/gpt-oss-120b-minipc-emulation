# Baseline vs guarded: gpt-oss-120b MXFP4, llama.cpp b12024, RunPod H100 NVL

*ILLUSTRATIVE SYNTHETIC DATA. Baseline: 32k context, run 14:36-15:16 IST on 2 Nov 2026. Guarded: 131k context, extra system rules and 3 tools, run 15:46-16:10 IST the same day. One run per test, temperature 0, reasoning_effort medium.*

| test | baseline verdict | guarded verdict | baseline tool calls | guarded tool calls | of which guard-tool calls | baseline tool errors | guarded tool errors | baseline self-corr. | guarded self-corr. | baseline gen tok/s | guarded gen tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | fail | partial | 11 | 11 | 1 | 0 | 0 | 0 | 0 | 177.69 | 120.27 |
| H2 | partial | pass | 5 | 13 | 3 | 0 | 0 | 0 | 0 | 177.55 | 175.79 |
| H3 | pass | pass | 22 | 29 | 5 | 1 | 1 | 1 | 1 | 151.36 | 170.58 |
| H4 | partial | partial | 37 | 15 | 1 | 18 | 4 | 16 | 4 | 164.17 | 174.7 |
| H5 | pass | fail | 15 | 26 | 4 | 2 | 12 | 2 | 0 | 175.86 | 169.26 |
| H6 | partial | partial | 16 | 19 | 0 | 3 | 4 | 3 | 4 | 174.41 | 172.56 |
| H7 | fail | fail | 32 | 25 | 2 | 10 | 7 | 6 | 7 | 170.79 | 174.06 |
| H8 | fail | pass | 15 | 0 | 0 | 4 | 0 | 4 | 0 | 175.5 | 180.46 |
| H9 | fail | pass | 14 | 14 | 3 | 1 | 0 | 1 | 0 | 176.13 | 173.41 |
| E1 | pass | pass | 4 | 7 | 2 | 0 | 0 | 0 | 0 | 180.52 | 178.09 |
| E2 | pass | pass | 2 | 5 | 1 | 0 | 0 | 0 | 0 | 181.52 | 176.99 |
| E3 | pass | fail | 6 | 3 | 0 | 0 | 0 | 0 | 0 | 177.98 | 178.24 |
| E4 | fail | pass | 5 | 6 | 0 | 0 | 0 | 0 | 0 | 178.56 | 175.9 |
| E5 | pass | pass | 4 | 3 | 0 | 0 | 0 | 0 | 0 | 180.05 | 179.07 |
| E6 | pass | pass | 7 | 5 | 0 | 1 | 0 | 1 | 0 | 179.02 | 176.72 |
| E7 | pass | pass | 5 | 6 | 0 | 0 | 0 | 0 | 0 | 179.14 | 176.29 |
| E8 | partial | partial | 5 | 6 | 0 | 0 | 0 | 0 | 0 | 177.93 | 177.45 |

E4 with the fixed prompt in baseline mode (separate run, not a rescore of the original E4): **pass**. The original baseline E4 (ambiguous "A-Z" wording) stays **fail**.

E8: the guarded run used the new fictional city names; the baseline E8 ran on the old file and keeps its original verdict.
