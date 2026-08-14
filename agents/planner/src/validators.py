"""
Validazione logica delle bozze di piano generate dalla pipeline (punto 4.1 della roadmap).

Volutamente disaccoppiato da Pydantic: opera sul dizionario grezzo restituito dal LLM, 
PRIMA della costruzione dei modelli (QueryResponse/PlanDay/TimeSlot). 
Questo permette di:
- validare bozze ancora malformate senza sollevare eccezioni bloccanti;
- produrre messaggi di errore discorsivi e leggibili, riutilizzabili sia per decidere 
  se innescare un retry, sia come feedback diretto da fornire al modello nel prompt di correzione.
"""

import re
from typing import Any

# Regex per la validazione dei formati temporali e delle date
_TIME_RE: re.Pattern[str] = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DATE_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MINUTES_PER_DAY: int = 24 * 60


def _parse_time(value: str) -> int:
    """
    Converte un orario in formato stringa 'HH:MM' in minuti dalla mezzanotte.

    Args:
        value (str): L'orario nel formato 'HH:MM'.

    Returns:
        int: I minuti totali calcolati a partire dalle 00:00.
    """
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _format_minutes(value: int) -> str:
    """
    Formatta i minuti totali dalla mezzanotte in una stringa 'HH:MM'.

    Args:
        value (int): I minuti totali.

    Returns:
        str: La stringa formattata (es. 90 -> '01:30').
    """
    return f"{value // 60:02d}:{value % 60:02d}"


def validate_draft(draft: dict[str, Any] | None, domain: str) -> list[str]:
    """
    Valida in modo difensivo una bozza di piano in formato dizionario.

    Analizza la struttura per individuare campi mancanti, tipi errati e
    incongruenze logiche (es. sovrapposizione di orari, durate impossibili).

    Args:
        draft (dict[str, Any] | None): Il dizionario del piano o None se il parsing è fallito.
        domain (str): Il dominio di destinazione (es. 'study', 'travel', 'routine').

    Returns:
        list[str]: Una lista di stringhe descrittive degli errori trovati. 
        Lista vuota se il piano è logicamente e strutturalmente valido.
    """
    if not draft:
        return ["il draft è vuoto o non è un oggetto JSON valido"]

    errors: list[str] = []
    
    # 1. Controlli top-level (allineati con QueryResponse)
    title: Any = draft.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("il campo 'title' è mancante o non è una stringa valida")

    summary: Any = draft.get("summary")
    if summary is not None and not isinstance(summary, str):
        errors.append("il campo 'summary' deve essere una stringa")
        
    contingency_notes: Any = draft.get("contingency_notes")
    if contingency_notes is not None:
        if not isinstance(contingency_notes, list) or not all(isinstance(x, str) for x in contingency_notes):
            errors.append("il campo 'contingency_notes' deve essere una lista di stringhe")

    days: Any = draft.get("days")
    if not days or not isinstance(days, list):
        errors.append("il campo 'days' è mancante, vuoto o non è una lista")
        return errors  # Inutile proseguire se mancano i giorni o non sono iterabili
    
    seen_indices: set[int] = set()

    for day in days:
        day_index: Any = day.get("day_index")
        
        # Se day_index manca o non è un numero intero positivo, interrompiamo la 
        # validazione di questo specifico giorno: i successivi messaggi di errore 
        # per gli slot necessitano del day_index per essere leggibili.
        if not isinstance(day_index, int) or day_index < 1:
            errors.append(f"day_index non valido: {day_index!r}")
            continue
            
        if day_index in seen_indices:
            errors.append(f"day_index {day_index} duplicato")
        seen_indices.add(day_index)

        # Controlli di tipo sul giorno (allineati con lo schema Pydantic PlanDay)
        label: Any = day.get("label")
        if label is not None and not isinstance(label, str):
            errors.append(f"giorno {day_index}: il campo 'label' deve essere una stringa")

        date_value: Any = day.get("date")
        if date_value is not None and not _DATE_RE.match(str(date_value)):
            errors.append(f"giorno {day_index}: campo 'date' malformato (atteso YYYY-MM-DD): {date_value!r}")

        slots: Any = day.get("slots") or []
        if not slots or not isinstance(slots, list):
            errors.append(f"giorno {day_index}: nessuno slot presente o formato non valido")
            continue

        total_minutes: int = 0
        
        # Struttura per accumulare gli slot ancorati a un orario di inizio esplicito
        # e verificare successivamente la presenza di sovrapposizioni temporali
        timed_slots: list[tuple[int, int, str]] = []  # (inizio_min, fine_min, task)

        for slot in slots:
            # Controlli di tipo su slot (allineati con TimeSlot).
            # Usiamo Any perché il JSON dell'LLM potrebbe non rispettare lo schema.
            task: Any = slot.get("task")
            if not isinstance(task, str) or not task.strip():
                errors.append(f"giorno {day_index}: il campo 'task' è mancante o non è una stringa")
                # Fallback per garantire che i messaggi di errore successivi 
                # per questo stesso slot non crashino cercando di stampare il task.
                task = str(task) if task else "?"
                
            category: Any = slot.get("category")
            if category is not None and not isinstance(category, str):
                errors.append(f"giorno {day_index} ('{task}'): il campo 'category' deve essere una stringa")

            subtasks: Any = slot.get("subtasks")
            if subtasks is not None:
                if not isinstance(subtasks, list) or not all(isinstance(x, str) for x in subtasks):
                    errors.append(f"giorno {day_index} ('{task}'): il campo 'subtasks' deve essere una lista di stringhe")

            notes: Any = slot.get("notes")
            if notes is not None and not isinstance(notes, str):
                errors.append(f"giorno {day_index} ('{task}'): il campo 'notes' deve essere una stringa")

            duration: Any = slot.get("duration_minutes")
            if not isinstance(duration, int) or duration <= 0:
                errors.append(f"giorno {day_index}: duration_minutes non valido per '{task}': {duration!r}")
                duration = 0
                
            total_minutes += duration

            start_time: Any = slot.get("start_time")
            if start_time is not None:
                if not isinstance(start_time, str) or not _TIME_RE.match(start_time):
                    errors.append(f"giorno {day_index}: start_time malformato per '{task}': {start_time!r}")
                    continue
                
                # Se l'orario è valido, calcoliamo i minuti assoluti e salviamo 
                # la finestra temporale per il successivo controllo sovrapposizioni.
                start_min: int = _parse_time(start_time)
                timed_slots.append((start_min, start_min + duration, task))

        # Verifica che il totale delle ore allocate in un giorno sia fisicamente possibile.
        if total_minutes > MINUTES_PER_DAY:
            errors.append(f"giorno {day_index}: durata totale {total_minutes} minuti supera le 24 ore")

        # Ordinamento cronologico e controllo delle sovrapposizioni tra gli slot ancorati.
        # Zip affianca ogni slot a quello cronologicamente successivo.
        timed_slots.sort()
        for (start_a, end_a, task_a), (start_b, end_b, task_b) in zip(timed_slots, timed_slots[1:]):
            if start_b < end_a:
                errors.append(
                    f"giorno {day_index}: sovrapposizione tra '{task_a}' (termina alle {_format_minutes(end_a)}) "
                    f"e '{task_b}' (inizia alle {_format_minutes(start_b)})"
                )

    # Vincoli specifici per dominio sulla sequenza e il numero dei giorni
    if domain == "routine":
        if seen_indices != set(range(1, 8)):
            errors.append(f"il dominio 'routine' richiede esattamente i giorni 1-7, trovati: {sorted(seen_indices)}")
    elif seen_indices and seen_indices != set(range(1, len(seen_indices) + 1)):
        errors.append(f"day_index deve formare una sequenza contigua a partire da 1, trovati: {sorted(seen_indices)}")

    return errors