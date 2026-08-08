from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    """stato condiviso nel grafo LangGraph."""
    question: str
    # knowledge graph scelto dall'utente; None lascia decidere il kg-agent
    target_kg: Optional[str]
    selected_agents: List[str]
    kg_results: Optional[Dict[str, Any]]
    planner_results: Optional[Dict[str, Any]]
    multiapi_results: Optional[Dict[str, Any]]
    final_response: str