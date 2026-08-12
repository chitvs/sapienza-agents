from validators import validate_draft


def _valid_study_draft() -> dict:
    return {
        "title": "Preparazione esame",
        "days": [
            {
                "day_index": 1,
                "slots": [
                    {"task": "Capitolo 1", "start_time": "09:00", "duration_minutes": 60, "category": "studio"},
                    {"task": "Esercizi capitolo 1", "start_time": "10:15", "duration_minutes": 30, "category": "esercizi"},
                ],
            },
            {
                "day_index": 2,
                "slots": [{"task": "Capitolo 2", "start_time": "09:00", "duration_minutes": 60, "category": "studio"}],
            },
        ],
    }


def test_valid_draft_has_no_errors():
    assert validate_draft(_valid_study_draft(), "study") == []


def test_empty_draft_is_invalid():
    assert validate_draft(None, "study") != []
    assert validate_draft({}, "study") != []


def test_missing_days_is_invalid():
    assert validate_draft({"title": "x"}, "study") != []


def test_empty_slots_flagged():
    draft = {"days": [{"day_index": 1, "slots": []}]}
    errors = validate_draft(draft, "study")
    assert any("nessuno slot" in e for e in errors)


def test_duplicate_day_index_flagged():
    draft = {
        "days": [
            {"day_index": 1, "slots": [{"task": "a", "duration_minutes": 30}]},
            {"day_index": 1, "slots": [{"task": "b", "duration_minutes": 30}]},
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("duplicato" in e for e in errors)


def test_non_contiguous_day_index_flagged_for_study():
    draft = {
        "days": [
            {"day_index": 1, "slots": [{"task": "a", "duration_minutes": 30}]},
            {"day_index": 3, "slots": [{"task": "b", "duration_minutes": 30}]},
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("sequenza contigua" in e for e in errors)


def test_routine_requires_exactly_seven_days():
    draft = {"days": [{"day_index": i, "slots": [{"task": "x", "duration_minutes": 30}]} for i in range(1, 6)]}
    errors = validate_draft(draft, "routine")
    assert any("giorni 1-7" in e for e in errors)


def test_zero_duration_flagged():
    draft = {"days": [{"day_index": 1, "slots": [{"task": "x", "duration_minutes": 0}]}]}
    errors = validate_draft(draft, "study")
    assert any("duration_minutes non valido" in e for e in errors)


def test_malformed_start_time_flagged():
    draft = {"days": [{"day_index": 1, "slots": [{"task": "x", "start_time": "9:00", "duration_minutes": 30}]}]}
    errors = validate_draft(draft, "study")
    assert any("start_time malformato" in e for e in errors)


def test_overlapping_slots_flagged():
    draft = {
        "days": [
            {
                "day_index": 1,
                "slots": [
                    {"task": "a", "start_time": "09:00", "duration_minutes": 90},
                    {"task": "b", "start_time": "10:00", "duration_minutes": 30},
                ],
            }
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("sovrapposizione" in e for e in errors)


def test_total_duration_over_24h_flagged():
    draft = {"days": [{"day_index": 1, "slots": [{"task": "x", "duration_minutes": 1500}]}]}
    errors = validate_draft(draft, "study")
    assert any("supera le 24 ore" in e for e in errors)


def test_malformed_date_flagged():
    draft = {"days": [{"day_index": 1, "date": "12-06-2026", "slots": [{"task": "x", "duration_minutes": 30}]}]}
    errors = validate_draft(draft, "travel")
    assert any("'date' malformato" in e for e in errors)


def test_invalid_title_type_flagged():
    draft = {
        "title": 123, # Errore: numero invece di stringa
        "days": [
            {"day_index": 1, "slots": [{"task": "Lettura", "duration_minutes": 30}]}
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("non è una stringa" in e for e in errors)

def test_invalid_task_type_flagged():
    draft = {
        "title": "Piano di studio",
        "days": [
            {
                "day_index": 1, 
                "slots": [{"task": 404, "duration_minutes": 30}] # Errore: numero
            }
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("non è una stringa" in e for e in errors)

def test_invalid_subtasks_flagged():
    draft = {
        "title": "Piano di studio",
        "days": [
            {
                "day_index": 1, 
                "slots": [{
                    "task": "Lettura", 
                    "duration_minutes": 30,
                    "subtasks": "dovrebbe essere una lista, non una stringa" # Errore
                }]
            }
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("lista di stringhe" in e for e in errors)

def test_invalid_category_type_flagged():
    draft = {
        "title": "Piano di studio",
        "days": [
            {
                "day_index": 1, 
                "slots": [{"task": "Ripasso", "duration_minutes": 30, "category": True}] # Errore: booleano
            }
        ]
    }
    errors = validate_draft(draft, "study")
    assert any("deve essere una stringa" in e for e in errors)