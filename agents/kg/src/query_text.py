"""Utilità di analisi testuale delle query, condivise fra traduttori ed esecutori."""

import re
from collections.abc import Callable

# I letterali riconoscono le sequenze di escape: senza \\. un apostrofo sfuggito (\')
# chiuderebbe la stringa in anticipo e il testo successivo verrebbe scambiato per codice.
_STRING_LITERAL = re.compile(
    r'"""(?:\\.|.)*?"""' r"|'''(?:\\.|.)*?'''" r'|"(?:\\.|[^"\\\n])*"' r"|'(?:\\.|[^'\\\n])*'",
    re.DOTALL,
)

def mask_literals(query: str) -> str:
    """Sbianca i letterali di stringa, per analizzare la struttura della query senza il loro contenuto."""
    # si sostituisce con spazi anziché accorciare: così gli offset restano allineati a
    # quelli della query originale, e chi cerca una graffa può usarne l'indice
    return _STRING_LITERAL.sub(lambda m: " " * len(m.group(0)), query)

def apply_outside_literals(query: str, transform: Callable[[str], str]) -> str:
    """Applica la trasformazione al solo codice, lasciando intatti i letterali di stringa."""
    # le normalizzazioni sintattiche corromperebbero altrimenti i titoli cercati: un film
    # "Episode IV ( 1977 )" diventerebbe "Episode IV (1977)", che nel grafo non esiste
    pieces: list[str] = []
    last = 0
    for match in _STRING_LITERAL.finditer(query):
        pieces.append(transform(query[last:match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(transform(query[last:]))
    return "".join(pieces)
