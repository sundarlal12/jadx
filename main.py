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
import threading
from collections import deque
from bson import ObjectId
from pathlib import Path
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

MAX_LOG_LINES = 2000  # keep last N lines only (avoid memory blowup)


class DecompileFromUrlReq(BaseModel):
    apk_url: str
    scan_id: str | None = None


def log(msg: str):
    print(msg, flush=True)


def init_job_logs(scan_id: str):
    # store logs as deque, JSON endpoint will convert to list
    JOBS[scan_id]["logs"] = deque(maxlen=MAX_LOG_LINES)


def push_log(scan_id: str, line: str):
    line = (line or "").rstrip("\n")
    if "logs" not in JOBS[scan_id]:
        init_job_logs(scan_id)
    JOBS[scan_id]["logs"].append(line)
    # also send to Render logs
    print(f"[{scan_id}] {line}", flush=True)


def run_jadx_stream(scan_id: str, output_dir: str, apk_path: str, timeout_sec: int = 3600):
    """
    Run JADX and stream stdout/stderr live into JOBS[scan_id]["logs"].
    """
    cmd = [
        "jadx",
        "--threads-count", "1",
        "--verbose",
        "--log-level", "DEBUG",
        "--show-bad-code",
        "-d", output_dir,
        apk_path
    ]

    push_log(scan_id, "Starting JADX with verbose logs...")
    push_log(scan_id, "CMD: " + " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge stderr into stdout
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    def reader():
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                push_log(scan_id, line)
        except Exception as e:
            push_log(scan_id, f"[log-reader-error] {e}")

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("JADX timed out")

    if proc.returncode != 0:
        raise RuntimeError(f"JADX failed with exit code {proc.returncode}")

    push_log(scan_id, "JADX finished successfully.")


def worker(scan_id: str, apk_url: str):
    try:
        JOBS[scan_id]["status"] = "downloading"
        init_job_logs(scan_id)
        push_log(scan_id, f"Downloading APK: {apk_url}")

        base_tmp = tempfile.mkdtemp(prefix="apk_scan_")
        output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
        os.makedirs(output_dir, exist_ok=True)

        apk_path = os.path.join(output_dir, "app.apk")

        # Download with redirects + good timeouts
        r = requests.get(apk_url, stream=True, timeout=(20, 300), allow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"Download failed. status={r.status_code}")

        total = 0
        with open(apk_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)

        push_log(scan_id, f"Download complete: {total/1024/1024:.2f} MB")

        JOBS[scan_id]["status"] = "decompiling"
        push_log(scan_id, "Running JADX...")

        # Stream JADX logs live
        run_jadx_stream(scan_id, output_dir, apk_path, timeout_sec=3600)

        JOBS[scan_id]["status"] = "done"
        JOBS[scan_id]["output_dir"] = output_dir
        JOBS[scan_id]["sources_dir"] = os.path.join(output_dir, "sources")
        JOBS[scan_id]["resources_dir"] = os.path.join(output_dir, "resources")
        push_log(scan_id, f"DONE. Output: {output_dir}")

    except Exception as e:
        JOBS[scan_id]["status"] = "error"
        JOBS[scan_id]["error"] = str(e)
        push_log(scan_id, f"ERROR: {e}")


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
        "status_url": f"/status/{scan_id}",
        "logs_url": f"/logs/{scan_id}",
    })


@app.get("/status/{scan_id}")
def status(scan_id: str):
    job = JOBS.get(scan_id)
    if not job:
        raise HTTPException(404, "scan_id not found")

    # convert deque to list for JSON serialization
    resp = dict(job)
    if "logs" in resp and isinstance(resp["logs"], deque):
        resp["logs"] = list(resp["logs"])
    return JSONResponse(resp)


@app.get("/logs/{scan_id}")
def get_logs(scan_id: str):
    job = JOBS.get(scan_id)
    if not job:
        raise HTTPException(404, "scan_id not found")

    logs = job.get("logs", deque())
    if isinstance(logs, deque):
        logs = list(logs)

    return JSONResponse({
        "scan_id": scan_id,
        "status": job.get("status"),
        "logs": logs
    })




def safe_join(base: str, *paths: str) -> str:
    """
    Prevent path traversal (../..).
    """
    base_path = Path(base).resolve()
    target = base_path.joinpath(*paths).resolve()
    if not str(target).startswith(str(base_path) + os.sep):
        raise HTTPException(400, "Invalid path")
    return str(target)

@app.get("/browse/{scan_id}")
def browse(scan_id: str, path: str = ""):
    """
    List directories/files for a scan_id.
    Example:
      /browse/<scan_id>?path=
      /browse/<scan_id>?path=sources
      /browse/<scan_id>?path=resources
    """
    scan_dir = os.path.join(OUTPUT_ROOT, f"scan_id_{scan_id}")
    if not os.path.isdir(scan_dir):
        raise HTTPException(404, "scan_id directory not found")

    target = safe_join(scan_dir, path) if path else scan_dir
    if not os.path.exists(target):
        raise HTTPException(404, "Path not found")

    if os.path.isfile(target):
        return JSONResponse({
            "scan_id": scan_id,
            "path": path,
            "type": "file",
            "name": os.path.basename(target),
            "size_bytes": os.path.getsize(target),
        })

    items = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        items.append({
            "name": name,
            "type": "dir" if os.path.isdir(full) else "file",
            "size_bytes": None if os.path.isdir(full) else os.path.getsize(full)
        })

    return JSONResponse({
        "scan_id": scan_id,
        "path": path,
        "type": "dir",
        "items": items
    })

@app.get("/file/{scan_id}")
def read_file(scan_id: str, path: str, max_kb: int = 256):
    """
    Read a text file content (preview) for a scan.
    Example:
      /file/<scan_id>?path=sources/com/test/MainActivity.java
    """
    scan_dir = os.path.join(OUTPUT_ROOT, f"scan_id_{scan_id}")
    if not os.path.isdir(scan_dir):
        raise HTTPException(404, "scan_id directory not found")

    target = safe_join(scan_dir, path)
    if not os.path.isfile(target):
        raise HTTPException(404, "File not found")

    # limit read
    max_bytes = max_kb * 1024
    size = os.path.getsize(target)

    with open(target, "rb") as f:
        data = f.read(min(size, max_bytes))

    # best-effort decode
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = str(data)

    return JSONResponse({
        "scan_id": scan_id,
        "path": path,
        "size_bytes": size,
        "truncated": size > max_bytes,
        "content": text
    })
