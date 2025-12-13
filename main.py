import os
import tempfile
import subprocess
from bson import ObjectId  # MongoDB ObjectId

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="JADX APK Decompiler")

JADDX_CLI_JAR = os.getenv("JADDX_CLI_JAR", "/opt/jadx/jadx-1.5.0/bin/jadx-cli.jar")


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout


@app.post("/decompile")
async def decompile(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files are allowed")

    # Generate MongoDB ObjectId
    scan_id = str(ObjectId())

    # Base temp directory
    base_tmp = tempfile.mkdtemp(prefix="apk_scan_")

    # Output dir must be: scan_id_<objectId>
    output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
    os.makedirs(output_dir, exist_ok=True)

    # Save APK inside scan folder
    apk_path = os.path.join(output_dir, file.filename)
    with open(apk_path, "wb") as f:
        f.write(await file.read())

    # Run JADX (creates sources/, resources/, etc. inside output_dir)
    run_cmd([
        "java", "-jar", JADDX_CLI_JAR,
        "-d", output_dir,
        apk_path
    ])

    return JSONResponse({
        "status": "ok",
        "scan_id": scan_id,
        "output_dir": output_dir,
        "sources_dir": os.path.join(output_dir, "sources"),
        "resources_dir": os.path.join(output_dir, "resources"),
    })
