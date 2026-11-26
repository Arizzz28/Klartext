"""Runs on the Owner's Windows PC (started by start_pc_backend.bat). It does three things:
  1. starts the normal backend on this PC (same code, same database, same file storage - read from the file .env.pc)
  2. starts a tunnel (cloudflared) so the internet can reach the PC, and reads the public https address from it
  3. every 30 seconds tells the normal server "I am online, my address is ..." (heartbeat)
Close the window (or switch the PC off) and the heartbeat stops: after 90 seconds everybody is on the normal server again.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main():
    env = HERE / ".env.pc"
    if not env.exists():
        sys.exit("File .env.pc is missing. Copy .env.pc.example to .env.pc and fill it in (see README, section PC server).")
    load_env(env)
    main_url = os.environ.get("MAIN_SERVER_URL", "").rstrip("/")
    secret = os.environ.get("PC_SECRET", "")
    port = int(os.environ.get("PC_PORT", "5055"))
    if not main_url or not secret or not os.environ.get("DATABASE_URL"):
        sys.exit("MAIN_SERVER_URL, PC_SECRET and DATABASE_URL must be set in .env.pc")

    state = {"url": os.environ.get("PC_PUBLIC_URL", "").rstrip("/")}

    def tunnel():
        exe = shutil.which("cloudflared") or str(HERE / "cloudflared.exe")
        if state["url"] or not Path(exe).exists() and not shutil.which("cloudflared"):
            if not state["url"]:
                print("[PC] cloudflared not found. Put cloudflared.exe next to this file, or set PC_PUBLIC_URL in .env.pc.")
            return
        p = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{port}"], stderr=subprocess.PIPE, text=True)
        for line in p.stderr:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m:
                state["url"] = m.group(0)
                print("[PC] public address:", state["url"], flush=True)

    def heartbeat():
        while True:
            if state["url"]:
                try:
                    req = urllib.request.Request(main_url + "/api/pc/heartbeat", data=json.dumps({"url": state["url"]}).encode(),
                                                 headers={"Content-Type": "application/json", "X-PC-Secret": secret}, method="POST")
                    urllib.request.urlopen(req, timeout=15).read()
                except Exception as e:                       # the normal server may be asleep (free plan) - try again
                    print("[PC] heartbeat failed:", e, flush=True)
            time.sleep(30)

    threading.Thread(target=tunnel, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    sys.path.insert(0, str(HERE))
    import app as app_module                                 # imported AFTER .env.pc is loaded
    from waitress import serve
    print(f"[PC] backend running on port {port}. Keep this window open.", flush=True)
    serve(app_module.app, host="127.0.0.1", port=port, threads=8)


if __name__ == "__main__":
    main()
