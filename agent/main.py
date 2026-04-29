import logging
from fastapi import FastAPI, HTTPException
from heartbeat import run_heartbeat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Moltbook Agent")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/heartbeat")
async def trigger_heartbeat():
    try:
        await run_heartbeat()
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Heartbeat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
