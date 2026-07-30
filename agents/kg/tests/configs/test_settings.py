from configs.settings import settings

def test_defaults():
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.default_target_kg == "wikidata"

def test_prompts_exist():
    assert settings.prompts_dir.exists()
    assert (settings.prompts_dir / "translate_sparql.txt").exists()
    assert (settings.prompts_dir / "correction.txt").exists()
