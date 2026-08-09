import os

class Settings:
    kg_agent_url: str = os.getenv("KG_AGENT_URL", "http://localhost:8000")
    planner_agent_url: str = os.getenv("PLANNER_AGENT_URL", "http://localhost:8001")
    multiapi_agent_url: str = os.getenv("MULTIAPI_AGENT_URL", "http://localhost:8002")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

settings = Settings()