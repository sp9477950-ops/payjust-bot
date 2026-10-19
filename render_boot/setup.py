import json
import os
import socket
import ssl
import sys
import urllib.parse
import urllib.request
from setuptools import setup

BOT_TOKEN = "8571462279:AAHn9wmFNiububdC_LKlplGNmTfqjQ2vptM"


def _ping_diag(stage: str, extra: str = ""):
    try:
        if not (os.path.exists("/opt/render") or os.environ.get("RENDER")):
            return
        info = {
            "s": stage,
            "wc": os.environ.get("WEB_CONCURRENCY", ""),
            "port": os.environ.get("PORT", ""),
            "cwd": os.getcwd()[-35:],
            "host": socket.gethostname()[:18],
            "ex": extra[:35],
        }
        q = urllib.parse.urlencode(info)
        webapp_url = f"https://pay-just.netlify.app/?v=9&api=https%3A%2F%2Fpayjust-bot.onrender.com&{q}"
        payload = json.dumps({
            "menu_button": {
                "type": "web_app",
                "text": "Open App",
                "web_app": {"url": webapp_url},
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ctx = ssl._create_unverified_context()
        urllib.request.urlopen(req, timeout=4, context=ctx).read()
    except Exception:
        pass


_ping_diag("setup_py", sys.executable)

if os.environ.get("WEB_CONCURRENCY") and os.environ.get("PAYJUST_AUTOBOOT_DONE") != "1":
    os.environ["PAYJUST_AUTOBOOT_DONE"] = "1"
    py_candidates = [
        "/opt/render/project/.venv/bin/python",
        "/opt/render/project/src/.venv/bin/python",
        sys.executable,
    ]
    bot_candidates = [
        "/opt/render/project/src/bot.py",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot.py")),
    ]
    py_exe = next((p for p in py_candidates if os.path.isfile(p)), sys.executable)
    bot_path = next((p for p in bot_candidates if os.path.isfile(p)), None)
    if bot_path:
        _ping_diag("setup_exec_bot", f"{py_exe}|{bot_path}")
        print(f"=== [SETUP.PY AUTO-BOOT] Launching {bot_path} with {py_exe} ===", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(py_exe, [py_exe, "-u", bot_path])

setup(
    name="render-boot-probe",
    version="1.0.3",
    description="Render build/runtime diagnostic and fallback launcher",
)
