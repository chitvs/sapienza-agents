import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[3]
src_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from fastapi import FastAPI
from api.routes import router as api_router

app = FastAPI(
    title="knowledge graph agent api",
    description="microservizio per interrogare knowledge graph in linguaggio naturale.",
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
