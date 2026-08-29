from typing import TypedDict, Any, Optional, Annotated

def merge_results(left: dict, right: dict) -> dict:
    """Reducer per unire i risultati di più agenti eseguiti in parallelo senza sovrascriverli."""
    return {**(left or {}), **(right or {})}

class AgentState(TypedDict, total=False):
    """Stato condiviso nel grafo LangGraph."""
    question: str
    language: str
    target_kg: Optional[str]
    selected_agents: list[str]
    final_response: str
    agent_results: Annotated[dict[str, Any], merge_results]