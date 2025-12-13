import os
import tempfile
import subprocess
from bson import ObjectId

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="APK Decompiler (JADX)")

JADDX_CLI_JAR = os.getenv("JADDX_CLI_JAR", "/opt/jadx/jadx-1.5.0/bin/jadx-cli.jar")

# Serve /static/index.html and /static/style.css
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout

@app.post("/decompile")
async def decompile(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files are allowed")

    scan_id = str(ObjectId())

    base_tmp = tempfile.mkdtemp(prefix="apk_scan_")
    output_dir = os.path.join(base_tmp, f"scan_id_{scan_id}")
    os.makedirs(output_dir, exist_ok=True)

    apk_path = os.path.join(output_dir, file.filename)
    with open(apk_path, "wb") as f:
        f.write(await file.read())

    # Run JADX: output_dir will contain sources/, resources/, etc.
    #run_cmd(["java", "-jar", JADDX_CLI_JAR, "-d", output_dir, apk_path])
    run_cmd(["jadx", "-d", output_dir, apk_path])

    return JSONResponse({
        "status": "ok",
        "scan_id": scan_id,
        "output_dir": output_dir,
        "sources_dir": os.path.join(output_dir, "sources"),
        "resources_dir": os.path.join(output_dir, "resources")
    })
