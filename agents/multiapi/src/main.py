import sys
from pathlib import Path

# risoluzione percorsi per import locali (come l'agente kg)
src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
    #Aggiungendo la cartella src/ al sys.path, tutti gli import interni funzionano sia in locale che dentro Docker.

from fastapi import FastAPI
from api.routes import router as api_router

app = FastAPI(
    title="Multi-API Agent",
    description="Microservizio che interroga API esterne (meteo, finanza, ecc.) in linguaggio naturale.",
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
