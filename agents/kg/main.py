from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="KG Agent (Mock)")


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query(req: QueryRequest):
    return {"results": [f"KG mock response per: {req.question}"]}
