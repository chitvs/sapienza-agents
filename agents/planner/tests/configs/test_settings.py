from configs.settings import settings


def test_defaults():
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.max_draft_retries >= 1


def test_prompts_exist():
    assert settings.prompts_dir.exists()
    assert (settings.prompts_dir / "classify_domain.txt").exists()
    assert (settings.prompts_dir / "draft_study.txt").exists()
    assert (settings.prompts_dir / "draft_travel.txt").exists()
    assert (settings.prompts_dir / "draft_routine.txt").exists()
    assert (settings.prompts_dir / "correct_draft.txt").exists()