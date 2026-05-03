from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import subprocess, datetime, asyncio
import mistune

app = FastAPI()
state = {"status": "idle", "last_event": None, "last_time": None}
subscribers = []

# Reading writeup
with open("static/writeup.md") as f:
    WRITEUP = f.read()
md = mistune.create_markdown(plugins=['math', 'table'])
writeup_html = md(WRITEUP)

# mounting js
app.mount("/static", StaticFiles(directory="static"), name="static")

async def broadcast():
    data = f"data: {state['status']} | {state['last_event']} | {state['last_time']}\n\n"
    for queue in subscribers:
        await queue.put(data)

@app.post("/trigger_rest")
async def trigger(event: dict):
    if state["status"] == "replaying":
        raise HTTPException(status_code=409, detail="Arm is busy replaying")
    
    state["last_event"] = event
    state["last_time"] = datetime.datetime.now().isoformat()
    state["status"] = "replaying"
    await broadcast() 
    asyncio.create_task(run_replay_rest())
    return {"ok": True, "status": "rest"}

@app.post("/trigger_aroused")
async def trigger(event: dict):
    if state["status"] == "replaying":
        raise HTTPException(status_code=409, detail="Arm is busy replaying")
    
    state["last_event"] = event
    state["last_time"] = datetime.datetime.now().isoformat()
    state["status"] = "replaying"
    await broadcast() 
    asyncio.create_task(run_replay_arouse())
    return {"ok": True, "status": "aroused"}

# TODO update to rest subroutine
async def run_replay_rest():
    proc = await asyncio.create_subprocess_exec(
        "lerobot-replay",
        "--robot.type=so101_follower",
        "--robot.port=/dev/ttyACM1",
        "--robot.id=polo",
        "--dataset.repo_id=binkd/pick_rest_can_and_place",
        "--dataset.episode=0"
    )
    await proc.wait()
    state["status"] = "idle"
    await broadcast()

# TODO update to aroused subroutine
async def run_replay_aroused():
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
    await broadcast()

@app.get("/events")
async def events():
    queue = asyncio.Queue()
    subscribers.append(queue)
    async def stream():
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            subscribers.remove(queue)
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
async def ui():
    return f"""
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script src="/static/stat.js"></script>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <div class="status-panel">
            <h1>Robot Status: <span id="status">loading...</span></h1>
            <p>Last event: <span id="event">-</span></p>
            <p>Time: <span id="time">-</span></p>
        </div>
        <hr>
        {writeup_html}
    </body>
    <footer>
        <p>© 2026 Nathanael Parra and Nathaniel Chappelle.
        Software: <a href="https://opensource.org/licenses/MIT">MIT License</a>.
        Content: <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
        Unless otherwise noted.</p>
    </footer>
    </html>
    """
