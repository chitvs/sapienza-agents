from pydantic import BaseModel, Field
from typing import Any

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        description="domanda in linguaggio naturale",
        json_schema_extra={"examples": ["Qual è la data di nascita di Albert Einstein?"]},
    )
    target_kg: str | None = Field(
        default="wikidata",
        description="knowledge graph target da interrogare: 'wikidata'",
    )

class QueryResponse(BaseModel):
    question: str
    target_kg: str = "wikidata"
    generated_query: str | None = None
    results: list[dict[str, Any]]
    count: int
    confidence: float = 1.0
    execution_time_ms: float | None = None
