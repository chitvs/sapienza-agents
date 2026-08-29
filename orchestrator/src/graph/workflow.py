from langgraph.graph import StateGraph, END
from src.config import settings
from src.graph.state import AgentState
from src.graph.nodes import supervisor_node, make_agent_node, unsupported_node, synthesizer_node

def _node_name(agent_name: str) -> str:
    return f"{agent_name.removesuffix('_agent')}_node"

def route_agents(state: AgentState) -> list[str]:
    """Instrada verso tutti gli agenti selezionati (in parallelo) o unsupported."""
    selected = state.get("selected_agents", [])
    valid_nodes = [_node_name(a) for a in selected if a in settings.agent_registry]
    
    if not valid_nodes:
        return ["unsupported"]
    return valid_nodes

def build_orchestrator_graph():
    """costruisce e compila lo StateGraph di LangGraph."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("unsupported", unsupported_node)

    # Registrazione dinamica nodi agenti
    node_names = []
    for agent_name in settings.agent_registry:
        node_name = _node_name(agent_name)
        workflow.add_node(node_name, make_agent_node(agent_name))
        
        # Fanning-in: tutti gli agenti convergono verso il sintetizzatore
        workflow.add_edge(node_name, "synthesizer")
        node_names.append(node_name)

    # Fanning-out: il supervisor lancia gli agenti in parallelo
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges("supervisor", route_agents, node_names + ["unsupported"])
    
    workflow.add_edge("synthesizer", END)
    workflow.add_edge("unsupported", END)

    return workflow.compile()

orchestrator_graph = build_orchestrator_graph()