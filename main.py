# import os
# import tempfile
# import subprocess
# from bson import ObjectId

# from fastapi import FastAPI, UploadFile, File, HTTPException
# from fastapi.responses import FileResponse, JSONResponse
# from fastapi.staticfiles import StaticFiles


# import requests

# from pydantic import BaseModel

# app = FastAPI(title="APK Decompiler (JADX)")

# JADDX_CLI_JAR = os.getenv("JADDX_CLI_JAR", "/opt/jadx/jadx-1.5.0/bin/jadx-cli.jar")

# # Serve /static/index.html and /static/style.css
# app.mount("/static", StaticFiles(directory="static"), name="static")

# @app.get("/")
# def home():
#     return FileResponse("static/index.html")

# def run_cmd(cmd):
#     p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
#     if p.returncode != 0:
#         raise RuntimeError(p.stderr.strip() or "Command failed")
#     return p.stdout

# class DecompileFromUrlReq(BaseModel):
#     apk_url: str
#     scan_id: str | None = None   # allow passing MongoDB ObjectId

# @app.post("/decompile")
# def decompile_from_url(payload: DecompileFromUrlReq):
#     scan_id = payload.scan_id or str(ObjectId())

#     base_tmp = tempfile.mkdtemp(prefix="apk_scan_")
#     output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
#     os.makedirs(output_dir, exist_ok=True)

#     apk_path = os.path.join(output_dir, "app.apk")

#     # Download APK
#     r = requests.get(payload.apk_url, stream=True, timeout=120)
#     if r.status_code != 200:
#         raise HTTPException(400, f"Failed to download APK, status={r.status_code}")

#     with open(apk_path, "wb") as f:
#         for chunk in r.iter_content(chunk_size=1024 * 1024):
#             if chunk:
#                 f.write(chunk)

#     # Run JADX (your Docker must have `jadx` installed and in PATH)
#     run_cmd(["jadx", "-d", output_dir, apk_path])

#     return JSONResponse({
#         "status": "ok",
#         "scan_id": scan_id,
#         "output_dir": output_dir,
#         "sources_dir": os.path.join(output_dir, "sources"),
#         "resources_dir": os.path.join(output_dir, "resources")
#     })


import os
import tempfile
import subprocess
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

app = FastAPI(title="APK Decompiler (JADX)")

# Static UI (optional)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

# Simple in-memory job store (Render restarts will clear it)
JOBS: Dict[str, Dict[str, Any]] = {}
EXEC = ThreadPoolExecutor(max_workers=1)  # keep 1 to avoid RAM blowups

class DecompileFromUrlReq(BaseModel):
    apk_url: str
    scan_id: str | None = None

def log(msg: str):
    print(msg, flush=True)

def run_cmd(cmd, timeout_sec=3600):
    # Capture output so you can see errors in logs
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Command failed").strip())
    return p.stdout

def worker(scan_id: str, apk_url: str):
    try:
        JOBS[scan_id]["status"] = "downloading"
        log(f"[{scan_id}] Downloading APK: {apk_url}")

        base_tmp = tempfile.mkdtemp(prefix="apk_scan_")
        output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
        os.makedirs(output_dir, exist_ok=True)

        apk_path = os.path.join(output_dir, "app.apk")

        # Download with good timeouts + redirects
        r = requests.get(apk_url, stream=True, timeout=(20, 300), allow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"Download failed. status={r.status_code}")

        total = 0
        with open(apk_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        log(f"[{scan_id}] Download complete: {total/1024/1024:.2f} MB")

        JOBS[scan_id]["status"] = "decompiling"
        log(f"[{scan_id}] Running JADX...")

        # IMPORTANT: reduce threads to avoid RAM OOM on small instances
        run_cmd([
            "jadx",
            "--threads-count", "1",
            "-d", output_dir,
            apk_path
        ], timeout_sec=3600)

        JOBS[scan_id]["status"] = "done"
        JOBS[scan_id]["output_dir"] = output_dir
        JOBS[scan_id]["sources_dir"] = os.path.join(output_dir, "sources")
        JOBS[scan_id]["resources_dir"] = os.path.join(output_dir, "resources")
        log(f"[{scan_id}] DONE. Output: {output_dir}")

    except Exception as e:
        JOBS[scan_id]["status"] = "error"
        JOBS[scan_id]["error"] = str(e)
        log(f"[{scan_id}] ERROR: {e}")

@app.post("/decompile")
def decompile_from_url(payload: DecompileFromUrlReq):
    scan_id = payload.scan_id or str(ObjectId())

    # create job record
    JOBS[scan_id] = {
        "status": "queued",
        "apk_url": payload.apk_url
    }

    # start background work
    EXEC.submit(worker, scan_id, payload.apk_url)

    return JSONResponse({
        "status": "accepted",
        "scan_id": scan_id,
        "status_url": f"/status/{scan_id}"
    })

@app.get("/status/{scan_id}")
def status(scan_id: str):
    job = JOBS.get(scan_id)
    if not job:
        raise HTTPException(404, "scan_id not found")

    return JSONResponse(job)
