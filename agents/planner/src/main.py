"""
Entrypoint principale del microservizio Planner Agent.

Configura l'applicazione FastAPI, registra i router per gli endpoint API 
(inclusi gli health check e il query processing) e avvia il server uvicorn
quando eseguito come script standalone.
"""

import sys
from pathlib import Path

# Risoluzione dinamica dei percorsi per gli import locali.
# Garantisce che i moduli dentro 'src' vengano trovati correttamente 
# anche se lo script viene avviato direttamente dalla root del progetto 
# senza PYTHONPATH preconfigurato.
src_dir: Path = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import uvicorn
from fastapi import FastAPI

from api.routes import router as api_router

app: FastAPI = FastAPI(
    title="Planner Agent",
    description="Microservizio che scompone richieste di pianificazione (studio, viaggi, routine) in piani strutturati.",
)

app.include_router(api_router)

if __name__ == "__main__":
    # Avvia il server di sviluppo se il file viene eseguito direttamente
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)