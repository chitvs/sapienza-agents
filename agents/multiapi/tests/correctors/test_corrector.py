from correctors.llm_response_corrector import LlmResponseCorrector


def test_corrector_succeeds_on_first_retry():
    """il corrector riesce al primo retry se il LLM restituisce JSON valido."""
    attempts = []

    def mock_llm(prompt: str) -> str:
        attempts.append(prompt)
        return '{"intent": "weather"}'

    def mock_clean(raw: str) -> str:
        return raw

    corrector = LlmResponseCorrector(max_retries=2)
    result = corrector.extract_json_with_retry(
        llm_generate_fn=mock_llm,
        clean_json_fn=mock_clean,
        original_prompt="test prompt",
        failed_response="not json at all",
    )
    assert result == {"intent": "weather"}
    assert len(attempts) == 1  # riuscito al primo tentativo


def test_corrector_succeeds_on_second_retry():
    """il corrector riesce al secondo retry."""
    call_count = [0]

    def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return "still broken"
        return '{"city": "Roma"}'

    def mock_clean(raw: str) -> str:
        return raw

    corrector = LlmResponseCorrector(max_retries=3)
    result = corrector.extract_json_with_retry(
        llm_generate_fn=mock_llm,
        clean_json_fn=mock_clean,
        original_prompt="test prompt",
        failed_response="bad json",
    )
    assert result == {"city": "Roma"}
    assert call_count[0] == 2


def test_corrector_fails_after_max_retries():
    """se il LLM continua a restituire JSON non valido, ritorna None."""

    def mock_llm(prompt: str) -> str:
        return "I cannot help you with that"

    def mock_clean(raw: str) -> str:
        return raw

    corrector = LlmResponseCorrector(max_retries=2)
    result = corrector.extract_json_with_retry(
        llm_generate_fn=mock_llm,
        clean_json_fn=mock_clean,
        original_prompt="test prompt",
        failed_response="not json",
    )
    assert result is None


def test_corrector_includes_failed_response_in_prompt():
    """il corrector include la risposta fallita nel prompt di correzione."""
    prompts_received = []

    def mock_llm(prompt: str) -> str:
        prompts_received.append(prompt)
        return '{"intent": "exchange_rate"}'

    def mock_clean(raw: str) -> str:
        return raw

    corrector = LlmResponseCorrector(max_retries=1)
    corrector.extract_json_with_retry(
        llm_generate_fn=mock_llm,
        clean_json_fn=mock_clean,
        original_prompt="original request",
        failed_response="this was the bad output",
    )
    assert "this was the bad output" in prompts_received[0]
    assert "original request" in prompts_received[0]
