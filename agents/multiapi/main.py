from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Multi-API Agent (Mock)")


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query(req: QueryRequest):
    return {"results": [f"Multi-API mock response per: {req.question}"]}
