"""Create / watch / terminate a RunPod GPU pod via the official RunPod REST API (https://rest.runpod.io/v1).
Reads RUNPOD_API_KEY from the environment only (never pass it on the command line, never commit it).

  python runpod_ctl.py up --hours 2          # create pod, arm auto-terminate, wait until llama-server is healthy
  python runpod_ctl.py status [POD_ID]       # show state + cost/hr
  python runpod_ctl.py url [POD_ID]          # print the OpenAI base URL
  python runpod_ctl.py terminate [POD_ID]    # delete the pod (stops all billing for it)
  python runpod_ctl.py list                  # all pods on the account (catch strays)
  python runpod_ctl.py up --dry-run          # print the request body, no API call
POD_ID defaults to the one saved in .pod_id by `up`."""
import argparse, base64, json, os, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path
import requests

API = "https://rest.runpod.io/v1"
HERE = Path(__file__).resolve().parent
POD_FILE = HERE / ".pod_id"
IMAGE = "runpod/pytorch:1.5.1-cu1281-torch280-ubuntu2404"   # Ubuntu 24.04, CUDA 12.8.1 (tag checked on Docker Hub 1 Nov 2026)
GPU = "NVIDIA A100-SXM4-80GB"

def _key():
    k = os.getenv("RUNPOD_API_KEY")
    if not k: sys.exit("RUNPOD_API_KEY is not set in the environment")
    return k

def _req(method, path, **kw):
    r = requests.request(method, API + path, headers={"Authorization": f"Bearer {_key()}"}, timeout=60, **kw)
    if r.status_code >= 400: raise RuntimeError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:500]}")
    return r.json() if r.text.strip() else {}

def proxy_url(pod_id, port=8000): return f"https://{pod_id}-{port}.proxy.runpod.net"

def body(hours, name, gpus=None, cloud="SECURE", ctx=None, gpu_count=1, setup_file="pod_setup.sh", min_ram=None, min_vcpu=None, extra_ports=()):
    import gzip; setup = base64.b64encode(gzip.compress((HERE / setup_file).read_bytes(), 9)).decode()
    start = ("echo $POD_SETUP_B64 | base64 -d | gunzip > /pod_setup.sh && chmod +x /pod_setup.sh; "
             "nohup bash /pod_setup.sh > /pod_setup.log 2>&1 & "
             "if [ -x /start.sh ]; then exec /start.sh; else sleep infinity; fi")
    return {"name": name, "imageName": IMAGE, "computeType": "GPU", "gpuTypeIds": gpus or [GPU], "gpuCount": gpu_count,
            "cloudType": cloud, "gpuTypePriority": "custom", "interruptible": False, "allowedCudaVersions": ["13.0", "12.9", "12.8"],
            "containerDiskInGb": 120, "volumeInGb": 0, "ports": ["8000/http", "22/tcp", *extra_ports],
            **({"minRAMPerGPU": min_ram} if min_ram else {}), **({"minVCPUPerGPU": min_vcpu} if min_vcpu else {}),
            "env": {"POD_SETUP_B64": setup, "AUTO_STOP_HOURS": str(hours), **({"CTX": str(int(ctx))} if ctx else {})},
            "dockerStartCmd": ["bash", "-c", start]}

def terminate(pod_id):
    try:
        _req("DELETE", f"/pods/{pod_id}"); print(f"terminated {pod_id} at {datetime.now():%H:%M} (local time)")
    except RuntimeError as e:
        if "404" in str(e): print(f"{pod_id} already gone")
        else: raise
    if POD_FILE.exists() and POD_FILE.read_text().strip() == pod_id: POD_FILE.unlink()

def arm_watchdog(pod_id, hours):
    """Detached local process that deletes the pod after `hours`, even if this script or the tests crash."""
    log = HERE / f"watchdog_{pod_id}.log"
    p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_watchdog", pod_id, str(hours)],
                         stdout=open(log, "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    print(f"local auto-terminate armed: pid {p.pid}, fires at {datetime.now() + timedelta(hours=hours):%H:%M} local time (log {log.name})")

def wait_ready(pod_id, max_min=45):
    url = proxy_url(pod_id); t0 = time.time(); last = ""
    while time.time() - t0 < max_min * 60:
        msg = ""
        try:
            pod = _req("GET", f"/pods/{pod_id}"); msg = f"pod {pod.get('desiredStatus')}"
            h = requests.get(url + "/health", timeout=15)
            msg += f", /health HTTP {h.status_code} {h.text[:60]!r}"
            if h.status_code == 200 and "ok" in h.text: print(f"READY after {(time.time()-t0)/60:.1f} min"); return True
        except Exception as e: msg += f" ({type(e).__name__})"
        if msg != last: print(f"[{(time.time()-t0)/60:5.1f} min] {msg}", flush=True); last = msg
        time.sleep(20)
    print(f"not ready after {max_min} min"); return False

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["up", "status", "url", "terminate", "list", "_watchdog"])
    ap.add_argument("pod_id", nargs="?"); ap.add_argument("hours_arg", nargs="?")
    ap.add_argument("--hours", type=float, default=2.0, help="hard auto-terminate after this many hours (default 2)")
    ap.add_argument("--name", default="gptoss120b-tooltest"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gpus", default=None, help="comma-separated GPU type ids in priority order"); ap.add_argument("--cloud", default="SECURE")
    ap.add_argument("--ctx", type=int, default=None, help="llama-server context size (pod falls back to 65536 if it does not fit)")
    ap.add_argument("--gpu-count", type=int, default=1); ap.add_argument("--setup", default="pod_setup.sh")
    ap.add_argument("--min-ram-per-gpu", type=int, default=None); ap.add_argument("--min-vcpu-per-gpu", type=int, default=None); ap.add_argument("--extra-port", action="append", default=[])
    ap.add_argument("--no-wait", action="store_true"); ap.add_argument("--ready-timeout-min", type=int, default=45)
    a = ap.parse_args()
    pid = a.pod_id or (POD_FILE.read_text().strip() if POD_FILE.exists() else None)

    if a.cmd == "_watchdog":
        h = float(a.hours_arg); print(f"{datetime.now():%F %H:%M} watchdog for {a.pod_id}: sleeping {h} h", flush=True)
        time.sleep(h * 3600)
        for i in range(10):
            try: terminate(a.pod_id); return
            except Exception as e: print("terminate failed:", e, flush=True); time.sleep(60)
        return
    if a.cmd == "up":
        b = body(a.hours, a.name, a.gpus.split(",") if a.gpus else None, a.cloud, a.ctx, a.gpu_count, a.setup, a.min_ram_per_gpu, a.min_vcpu_per_gpu, a.extra_port)
        if a.dry_run:
            show = dict(b, env={**b["env"], "POD_SETUP_B64": f"<{len(b['env']['POD_SETUP_B64'])} chars of base64 pod_setup.sh>"})
            print(json.dumps(show, indent=1)); return
        if pid: sys.exit(f"a pod is already recorded in .pod_id ({pid}); terminate it first")
        pod = _req("POST", "/pods", json=b); pid = pod["id"]; POD_FILE.write_text(pid)
        print(f"created pod {pid}  costPerHr={pod.get('costPerHr')}  machine={json.dumps(pod.get('machine', {}))[:200]}")
        arm_watchdog(pid, a.hours)
        print("OpenAI base URL:", proxy_url(pid) + "/v1")
        if not a.no_wait:
            ok = wait_ready(pid, a.ready_timeout_min)
            if not ok: print("Check the pod log in the RunPod console (/pod_setup.log). Terminate with: python runpod_ctl.py terminate")
        return
    if a.cmd == "list":
        for p in _req("GET", "/pods") or []: print(p.get("id"), p.get("name"), p.get("desiredStatus"), p.get("costPerHr"))
        return
    if not pid: sys.exit("no POD_ID given and no .pod_id file")
    if a.cmd == "status":
        p = _req("GET", f"/pods/{pid}")
        print(json.dumps({k: p.get(k) for k in ("id", "name", "desiredStatus", "costPerHr", "lastStartedAt", "gpu", "image", "memoryInGb", "vcpuCount", "machine")}, indent=1, default=str))
    elif a.cmd == "url": print(proxy_url(pid) + "/v1")
    elif a.cmd == "terminate": terminate(pid)

if __name__ == "__main__":
    main()
