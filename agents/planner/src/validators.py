"""
Validazione logica delle bozze di piano generate dalla pipeline (punto 4.1 della roadmap).

Volutamente disaccoppiato da Pydantic: opera sul dict grezzo restituito dal LLM, PRIMA
della costruzione dei modelli (QueryResponse/PlanDay/TimeSlot), così da:
- poter validare bozze ancora malformate senza sollevare eccezioni;
- produrre messaggi di errore leggibili, riusabili sia per decidere se innescare un
  retry sia come feedback da ridare al modello nel prompt di correzione.
"""

import re

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MINUTES_PER_DAY = 24 * 60


def _parse_time(value: str) -> int:
    """converte 'HH:MM' in minuti dalla mezzanotte."""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _format_minutes(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def validate_draft(draft: dict | None, domain: str) -> list[str]:
    """valida una bozza di piano. Restituisce una lista di errori (vuota se valida)."""
    if not draft:
        return ["il draft è vuoto o non è un oggetto JSON valido"]

    days = draft.get("days")
    if not days or not isinstance(days, list):
        return ["il campo 'days' è mancante, vuoto o non è una lista"]

    errors: list[str] = []
    seen_indices: set[int] = set()

    for day in days:
        day_index = day.get("day_index")
        if not isinstance(day_index, int) or day_index < 1:
            errors.append(f"day_index non valido: {day_index!r}")
            continue
        if day_index in seen_indices:
            errors.append(f"day_index {day_index} duplicato")
        seen_indices.add(day_index)

        date_value = day.get("date")
        if date_value is not None and not _DATE_RE.match(str(date_value)):
            errors.append(f"giorno {day_index}: campo 'date' malformato (atteso YYYY-MM-DD): {date_value!r}")

        slots = day.get("slots") or []
        if not slots:
            errors.append(f"giorno {day_index}: nessuno slot presente")
            continue

        total_minutes = 0
        timed_slots: list[tuple[int, int, str]] = []  # (inizio, fine, task) per slot con orario definito

        for slot in slots:
            task = slot.get("task", "?")
            duration = slot.get("duration_minutes")
            if not isinstance(duration, int) or duration <= 0:
                errors.append(f"giorno {day_index}: duration_minutes non valido per '{task}': {duration!r}")
                duration = 0
            total_minutes += duration

            start_time = slot.get("start_time")
            if start_time is not None:
                if not _TIME_RE.match(str(start_time)):
                    errors.append(f"giorno {day_index}: start_time malformato per '{task}': {start_time!r}")
                    continue
                start_min = _parse_time(start_time)
                timed_slots.append((start_min, start_min + duration, task))

        if total_minutes > MINUTES_PER_DAY:
            errors.append(f"giorno {day_index}: durata totale {total_minutes} minuti supera le 24 ore")

        timed_slots.sort()
        for (start_a, end_a, task_a), (start_b, end_b, task_b) in zip(timed_slots, timed_slots[1:]):
            if start_b < end_a:
                errors.append(
                    f"giorno {day_index}: sovrapposizione tra '{task_a}' (termina alle {_format_minutes(end_a)}) "
                    f"e '{task_b}' (inizia alle {_format_minutes(start_b)})"
                )

    # vincoli specifici per dominio sulla sequenza dei giorni
    if domain == "routine":
        if seen_indices != set(range(1, 8)):
            errors.append(f"il dominio 'routine' richiede esattamente i giorni 1-7, trovati: {sorted(seen_indices)}")
    elif seen_indices and seen_indices != set(range(1, len(seen_indices) + 1)):
        errors.append(f"day_index deve formare una sequenza contigua a partire da 1, trovati: {sorted(seen_indices)}")

    return errors