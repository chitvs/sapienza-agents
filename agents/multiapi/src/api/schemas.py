from pydantic import BaseModel, Field
from typing import Any

#Definisce la forma dei dati in entrata e uscita usando Pydantic
class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        description="domanda in linguaggio naturale",
        json_schema_extra={"examples": ["Che tempo fa a Roma?"]},
    )


class QueryResponse(BaseModel):
    question: str
    intent: str #che tipo di domanda è (es:"weather")
    results: list[dict[str, Any]] #lista di dizionari con i dati (es: temp, humidity)
    count: int #numero di risultati
    confidence: float = 1.0 
    execution_time_ms: float | None = None
    cached: bool = False #risposta servita dalla cache invece che dalle api
