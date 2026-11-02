# Tough pack scoresheet: gpt-oss-120b MXFP4 llama.cpp (NVIDIA H100 NVL, COMMUNITY) baseline, E4 fixed prompt

- **label**: gpt-oss-120b MXFP4 llama.cpp (NVIDIA H100 NVL, COMMUNITY) baseline, E4 fixed prompt
- **mode**: baseline
- **base_url**: RunPod HTTP proxy (pod terminated)
- **server**: {"model": "/workspace/models/gpt-oss-120b-MXFP4.gguf", "n_ctx": 131072, "build": "b12024-ddf48f85c"}
- **reasoning_effort**: medium
- **run_at**: 2026-11-02 16:10 IST
- **total_wall_min**: 0.2
- **totals**: 1 pass / 0 partial / 0 fail
- **settings**: max_steps 40, max_tokens/turn 8192, ctx 131072, trims at 20000 tokens
- **data_note**: ILLUSTRATIVE SYNTHETIC DATA - made-up supply network, no real company data or plant names
- **seed**: 20261102
- **plants**: 6
- **intermediate_units**: 2
- **depots**: 40
- **districts**: 300
- **history_months**: 36
- **h1_raw_invoice_rows**: 26935
- **h4_invoices**: 200
- **excel_round_data**: E1-E8: sales.xlsx 150 orders x 9 cols + Products (5); sales_dups.xlsx 157 rows (7 exact dups); customers.xlsx 40 messy rows - illustrative synthetic

| test | verdict | reason | tool_calls | tool_errors | self_corrections | steps | wall_s | gen_tok_s | prompt_tok_s | stop |
|---|---|---|---|---|---|---|---|---|---|---|
| E4 | pass | formula cells ok 15/15, values ok 15/15, two-criteria SUMIFS ok=True; e.g. A2..B2 =SUMIFS(Sales!$H:$H, Sales!$D:$D, "Central") | 6 | 0 | 0 | 6 | 11.1 | 177.22 | 2230.92 | submitted |

## Answers and checker details

### E4: Excel: SUMIFS/COUNTIFS/AVERAGEIFS summary formulas (pass)
- answer: `{"file": "e4.xlsx", "notes": "Created Summary sheet with region formulas and North_PPC_Revenue cell"}`
- details: `{"file": "e4.xlsx", "formula_cells_ok": 15, "value_cells_ok": 15, "expected": 15, "north_ppc_ok": true, "F2": "=SUMIFS(Sales!$H:$H, Sales!$D:$D, \"North\", Sales!$F:$F, \"Blend-P\")", "sample_B2": "=SUMIFS(Sales!$H:$H, Sales!$D:$D, \"Central\")"}`

