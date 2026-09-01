import os

class Settings:
    kg_agent_url: str = os.getenv("KG_AGENT_URL", "http://localhost:8000")
    planner_agent_url: str = os.getenv("PLANNER_AGENT_URL", "http://localhost:8001")
    multiapi_agent_url: str = os.getenv("MULTIAPI_AGENT_URL", "http://localhost:8002")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    agent_descriptions: dict[str, str] = {
        "kg_agent": (
            "fatti enciclopedici statici su entità nominate (persone, luoghi, opere, organizzazioni) "
            "e sulle relazioni fra di esse. NON per dati che cambiano nel tempo."
        ),
        "planner_agent": (
            "pianificazione e scomposizione di attività complesse (piano di studio, itinerario, routine). "
            "È autonomo nel recuperare qualsiasi contesto aggiuntivo di cui ha bisogno."
        ),
        "multiapi_agent": (
            "dati in tempo reale che richiedono un'api esterna: meteo e temperatura attuali di una città, "
            "tasso di cambio e conversione fra due valute, ora locale corrente o fuso orario, "
            "informazioni su un paese (capitale, popolazione, superficie, lingue, valuta, confini)."
        ),
    }
    agent_request_timeout_seconds: float = float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "330"))
    out_of_scope_message: str = os.getenv(
        "ORCHESTRATOR_OUT_OF_SCOPE_MESSAGE",
        "Nessun agente disponibile è in grado di gestire questa richiesta.",
    )

    @property
    def agent_registry(self) -> dict[str, str]:
        """Unica fonte di verità nome-agente -> url: usata sia per il routing sia per l'invocazione."""
        return {
            "kg_agent": self.kg_agent_url,
            "planner_agent": self.planner_agent_url,
            "multiapi_agent": self.multiapi_agent_url,
        }

settings = Settings()