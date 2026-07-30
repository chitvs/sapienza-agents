from langgraph.graph import StateGraph, END
from src.graph.state import AgentState
from src.graph.nodes import (
    supervisor_node,
    kg_node,
    planner_node,
    multiapi_node,
    synthesizer_node,
)

def route_agents(state: AgentState) -> list[str]:
    """funzione di routing condizionale per l'esecuzione in parallelo."""
    selected = state.get("selected_agents", [])
    routes = []
    if "kg_agent" in selected:
        routes.append("kg_node")
    if "planner_agent" in selected or "planner" in selected:
        routes.append("planner_node")
    if "multiapi_agent" in selected or "multiapi" in selected:
        routes.append("multiapi_node")
    
    # Se nessun agente è stato selezionato dal supervisor, vai subito al sintetizzatore
    return routes if routes else ["synthesizer"]

def build_orchestrator_graph():
    """costruisce e compila lo StateGraph di LangGraph."""
    workflow = StateGraph(AgentState)

    # registrazione dei nodi
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("kg_node", kg_node)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("multiapi_node", multiapi_node)
    workflow.add_node("synthesizer", synthesizer_node)

    # entrypoint del grafo
    workflow.set_entry_point("supervisor")

    # routing condizionale dal supervisor verso gli agenti
    workflow.add_conditional_edges("supervisor", route_agents, ["kg_node", "planner_node", "multiapi_node", "synthesizer"])

    # confluenza dagli agenti verso il sintetizzatore
    workflow.add_edge("kg_node", "synthesizer")
    workflow.add_edge("planner_node", "synthesizer")
    workflow.add_edge("multiapi_node", "synthesizer")

    # fine del workflow
    workflow.add_edge("synthesizer", END)

    return workflow.compile()

orchestrator_graph = build_orchestrator_graph()