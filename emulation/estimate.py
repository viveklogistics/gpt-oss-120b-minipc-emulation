"""Turn the emulation pod's measurements into ESTIMATES for the real mini PC (64 GB DDR4 + 22/12 GB eGPUs over USB4).
These are estimates, not measurements. Usage: python emulation/estimate.py [folder with bench.json + final_config.json]
Defaults: pod pinned STREAM triad 75.3 GB/s, pod PCIe H2D 57.6 GB/s, target RAM 42-51 GB/s, USB4 tunnel 3.0-3.8 GB/s."""
import json, sys
from pathlib import Path
F = Path(sys.argv[1] if len(sys.argv) > 1 else "results/minipc_emulation/server_and_bench")
d = json.load(open(F / "bench.json")); fc = json.load(open(F / "final_config.json"))
B = fc["cpu_active_bytes_per_token"] / 1e9   # GB of CPU-resident active expert weights read per generated token
E = fc["cpu_expert_bytes"] / 1e9             # GB of CPU-resident expert weights copied to the GPU per prompt micro-batch
BWP, PCIE = 75.3, 57.6
def gen(g, bw): return 1 / (1 / g + B * (1 / bw - 1 / BWP))            # add the extra RAM-read time per token
def pp(n, p, usb):                                                      # swap the PCIe copy time for a USB4 copy time
    ub = max(1, n / 2048); t = n / p; t2 = t - ub * E / PCIE + ub * E / usb; return n / t2, t2
g = d["decode_median_tok_s"]
print(f"short-prompt decode on pod {g:.1f} tok/s -> ESTIMATE {gen(g, 42):.1f} (42 GB/s) to {gen(g, 51):.1f} (51 GB/s) tok/s")
print("prompt_tokens | pod pp tok/s | pod TTFT s | pod gen tok/s | correct | EST pp tok/s | EST TTFT s | EST gen tok/s")
for L in d["long"]:
    n, p, gg = L["prompt_tokens"], L["pp_tok_s"], L["gen_tok_s"]; a, b = pp(n, p, 3.0), pp(n, p, 3.8)
    print(f"{n} | {p:.0f} | {L['ttft_s']:.1f} | {gg:.1f} | {L['qty_correct']} | {a[0]:.0f}-{b[0]:.0f} | {b[1]:.0f}-{a[1]:.0f} | {gen(gg, 42):.1f}-{gen(gg, 51):.1f}")
