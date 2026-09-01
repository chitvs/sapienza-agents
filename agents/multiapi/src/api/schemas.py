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
    ignored_intents: list[str] = Field(
        default_factory=list,
        description=(
            "temi riconosciuti nella domanda ma lasciati senza risposta, perché "
            "eccedono il numero di intent servibili per richiesta. Permette al "
            "chiamante di segnalare che la risposta copre solo parte della domanda."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "valorizzato quando nessun risultato è utilizzabile. I chiamanti "
            "(planner, orchestratore) verificano il fallimento a questo livello, "
            "non ispezionando i singoli elementi di results."
        ),
    )
