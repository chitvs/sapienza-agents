"""
Test per _finalize: formula di confidence additiva con
floor, su tutte le combinazioni draft_attempts x lista errori vuota/non vuota - incluso
il caso limite in cui il floor assorbe già la penalità di rete - e il salvataggio di gathered_context/contingency_notes.
"""

from api.schemas import QueryRequest
from pipeline import PlannerPipeline

_VALID_DRAFT = {
    "title": "Piano di prova",
    "days": [{"day_index": 1, "slots": [{"task": "studio", "duration_minutes": 60}]}],
}

_REQUEST = QueryRequest(question="domanda di prova")


def _finalize(draft_attempts, errors, context=None):
    pipeline = PlannerPipeline(verbose=True)
    return pipeline._finalize(_REQUEST, "study", _VALID_DRAFT, 10.0, draft_attempts, context or {}, errors)


def test_no_retries_no_errors():
    response = _finalize(0, [])
    assert response.confidence == 1.0
    assert response.contingency_notes is None


def test_no_retries_with_one_error():
    response = _finalize(0, ["kg-agent: timeout dopo 60.0s"])
    assert response.confidence == 0.9
    assert response.contingency_notes == ["kg-agent: timeout dopo 60.0s"]


def test_no_retries_with_two_errors_penalty_stays_flat():
    """la penalità è flat (-0.1) indipendentemente dal numero di errori nella lista."""
    response = _finalize(0, ["kg-agent: timeout dopo 60.0s", "multiapi-agent: errore HTTP 500"])
    assert response.confidence == 0.9
    assert response.contingency_notes == ["kg-agent: timeout dopo 60.0s", "multiapi-agent: errore HTTP 500"]


def test_one_retry_with_errors():
    response = _finalize(1, ["kg-agent: timeout dopo 60.0s"])
    assert response.confidence == 0.65


def test_two_retries_floor_absorbs_network_penalty():
    response_no_errors = _finalize(2, [])
    response_with_errors = _finalize(2, ["kg-agent: timeout dopo 60.0s"])
    assert response_no_errors.confidence == 0.5
    assert response_with_errors.confidence == 0.5


def test_empty_days_forces_zero_confidence_regardless_of_errors():
    pipeline = PlannerPipeline(verbose=True)
    response = pipeline._finalize(_REQUEST, "study", {"title": "x", "days": []}, 10.0, 0, {}, [])
    assert response.confidence == 0.0


def test_gathered_context_is_saved_on_response():
    response = _finalize(0, [], context={"kg_agent": {"x": 1}})
    assert response.gathered_context == {"kg_agent": {"x": 1}}


def test_empty_context_is_saved_as_none():
    response = _finalize(0, [], context={})
    assert response.gathered_context is None


def test_context_errors_are_appended_to_existing_contingency_notes():
    pipeline = PlannerPipeline(verbose=True)
    draft = dict(_VALID_DRAFT, contingency_notes=["nota del drafting"])
    response = pipeline._finalize(
        _REQUEST, "travel", draft, 10.0, 0, {}, ["kg-agent: timeout dopo 60.0s"]
    )
    assert response.contingency_notes == ["nota del drafting", "kg-agent: timeout dopo 60.0s"]