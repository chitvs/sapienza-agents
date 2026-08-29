import re
import time
from typing import Any

# usato quando né il chiamante né il costruttore indicano una durata
DEFAULT_TTL_SECONDS = 300.0


class ResponseCache:
    """cache in-memory per memorizzare i risultati delle query multiapi.

    Normalizza la domanda (minuscolo, senza punteggiatura) come chiave.
    Ogni voce ha una scadenza: i dati serviti da questo agente sono in tempo
    reale, quindi una risposta riusata troppo a lungo è semplicemente sbagliata.
    Quando la cache è piena, rimuove l'elemento più vecchio in stile FIFO.
    """

    def __init__(self, capacity: int = 100, default_ttl: float = DEFAULT_TTL_SECONDS):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self._cache: dict[str, dict[str, Any]] = {}

    def _normalize_key(self, text: str) -> str:
        """normalizza la stringa della domanda: minuscolo, rimuovi punteggiatura, collassa spazi."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return " ".join(text.split())

    def _purge_expired(self):
        """elimina le voci scadute.

        Serve prima dell'eviction: senza, una voce morta occuperebbe un posto e
        farebbe sfrattare una voce ancora valida.
        """
        now = time.monotonic()
        for key in [k for k, e in self._cache.items() if now >= e["expires_at"]]:
            del self._cache[key]

    def get(self, question: str) -> dict[str, Any] | None:
        """restituisce {"intent": str, "results": list[dict]} se la domanda è in cache e non è scaduta."""
        key = self._normalize_key(question)
        entry = self._cache.get(key)
        if entry is None:
            return None

        if time.monotonic() >= entry["expires_at"]:
            del self._cache[key]
            return None

        return {
            "intent": entry["intent"],
            "results": entry["results"],
            "ignored": entry.get("ignored", []),
        }

    def set(self, question: str, intent: str, results: list[dict],
            ttl: float | None = None, ignored: list[str] | None = None):
        """memorizza intent e risultati per la domanda specificata.

        Args:
            ttl: durata di validità in secondi. None usa `default_ttl`; un valore
                <= 0 significa "non memorizzare", perché quel dato invecchia
                troppo in fretta per poter essere riusato.
        """
        ttl = self.default_ttl if ttl is None else ttl
        if ttl <= 0:
            return

        key = self._normalize_key(question)
        self._purge_expired()

        if key not in self._cache and len(self._cache) >= self.capacity:
            # rimuovi il primo elemento inserito (FIFO)
            first_key = next(iter(self._cache))
            del self._cache[first_key]

        self._cache[key] = {
            "intent": intent,
            "results": results,
            "ignored": ignored or [],
            "expires_at": time.monotonic() + ttl,
        }

    def clear(self):
        """svuota la cache."""
        self._cache.clear()
