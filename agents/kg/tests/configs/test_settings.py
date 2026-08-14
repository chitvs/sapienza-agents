from configs.settings import settings
from models.llm import PROMPTS_DIR

def test_defaults():
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "qwen2.5-coder:7b"
    assert settings.default_target_kg == "wikidata"

def test_prompts_exist():
    assert PROMPTS_DIR.exists()
    assert (PROMPTS_DIR / "translate_sparql.txt").exists()
    assert (PROMPTS_DIR / "correction.txt").exists()
