from configs.settings import settings

def test_defaults():
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "qwen2.5-coder:7b"
    assert settings.default_target_kg == "wikidata"

def test_prompts_exist():
    assert settings.prompts_dir.exists()
    assert (settings.prompts_dir / "translate_sparql.txt").exists()
    assert (settings.prompts_dir / "correction.txt").exists()
