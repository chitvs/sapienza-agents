from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Planner Agent (Mock)")


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query(req: QueryRequest):
    return {"results": [f"Planner mock response per: {req.question}"]}
