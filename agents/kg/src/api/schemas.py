from typing import Any

from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        description="domanda in linguaggio naturale, in inglese",
        json_schema_extra={"examples": ["What is the birth date of Albert Einstein?"]},
    )
    target_kg: str | None = Field(
        default="wikidata",
        description="knowledge graph da interrogare: 'wikidata', 'dbpedia' o 'neo4j'",
    )

class QueryResponse(BaseModel):
    question: str
    target_kg: str = "wikidata"
    generated_query: str | None = None
    results: list[dict[str, Any]]
    count: int
    confidence: float = 1.0
    execution_time_ms: float | None = None
    cached: bool = False
