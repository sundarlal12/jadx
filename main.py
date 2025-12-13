import os
import tempfile
import subprocess
from bson import ObjectId

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


import requests

from pydantic import BaseModel

app = FastAPI(title="APK Decompiler (JADX)")

JADDX_CLI_JAR = os.getenv("JADDX_CLI_JAR", "/opt/jadx/jadx-1.5.0/bin/jadx-cli.jar")

# Serve /static/index.html and /static/style.css
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

def run_cmd(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "Command failed")
    return p.stdout

class DecompileFromUrlReq(BaseModel):
    apk_url: str
    scan_id: str | None = None   # allow passing MongoDB ObjectId

@app.post("/decompile")
def decompile_from_url(payload: DecompileFromUrlReq):
    scan_id = payload.scan_id or str(ObjectId())

    base_tmp = tempfile.mkdtemp(prefix="apk_scan_")
    output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
    os.makedirs(output_dir, exist_ok=True)

    apk_path = os.path.join(output_dir, "app.apk")

    # Download APK
    r = requests.get(payload.apk_url, stream=True, timeout=120)
    if r.status_code != 200:
        raise HTTPException(400, f"Failed to download APK, status={r.status_code}")

    with open(apk_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    # Run JADX (your Docker must have `jadx` installed and in PATH)
    run_cmd(["jadx", "-d", output_dir, apk_path])

    return JSONResponse({
        "status": "ok",
        "scan_id": scan_id,
        "output_dir": output_dir,
        "sources_dir": os.path.join(output_dir, "sources"),
        "resources_dir": os.path.join(output_dir, "resources")
    })
