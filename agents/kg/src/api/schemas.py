from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        description="domanda in linguaggio naturale",
        json_schema_extra={"examples": ["Qual è la data di nascita di Albert Einstein?"]},
    )
    target_kg: str | None = Field(
        default=None,
        description="knowledge graph target da interrogare: 'wikidata'",
    )

class QueryResponse(BaseModel):
    question: str
    target_kg: str
    generated_query: str | None = None
    results: list[dict]
    count: int
