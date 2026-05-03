from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import subprocess, datetime, asyncio

app = FastAPI()
state = {"status": "idle", "last_event": None, "last_time": None}

@app.post("/trigger")
async def trigger(event: dict):
    if state["status"] == "replaying":
        raise HTTPException(status_code=409, detail="Arm is busy replaying")
    
    state["last_event"] = event
    state["last_time"] = datetime.datetime.now().isoformat()
    state["status"] = "replaying"
    
    asyncio.create_task(run_replay())
    return {"ok": True}

async def run_replay():
    proc = await asyncio.create_subprocess_exec(
        "lerobot-replay",
        "--robot.type=so101_follower",
        "--robot.port=/dev/ttyACM1",
        "--robot.id=polo",
        "--dataset.repo_id=binkd/pick_and_place",
        "--dataset.episode=0"
    )
    await proc.wait()
    state["status"] = "idle"

@app.get("/", response_class=HTMLResponse)
async def ui():
    return f"""
    <html>
    <head><meta http-equiv="refresh" content="2"></head>
    <body>
        <h1>Robot Status: {state['status']}</h1>
        <p>Last event: {state['last_event']}</p>
        <p>Time: {state['last_time']}</p>
    </body>
    </html>
    """
