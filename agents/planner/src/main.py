import sys
from pathlib import Path

# risoluzione percorsi per import locali
src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from fastapi import FastAPI
from api.routes import router as api_router

app = FastAPI(
    title="Planner Agent",
    description="Microservizio che scompone richieste di pianificazione (studio, viaggi, routine) in piani strutturati.",
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)