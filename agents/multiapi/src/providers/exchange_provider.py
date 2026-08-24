import logging
from datetime import date
from typing import Any

import requests

from configs.settings import settings

logger = logging.getLogger(__name__)

# frankfurter pubblica i tassi di riferimento BCE, che partono dal 1999
FIRST_AVAILABLE_DATE = date(1999, 1, 4)


class ExchangeProvider:
    """provider di cambio valute basato su frankfurter (nessuna api key necessaria).

    Oltre al tasso, converte un importo e accetta una data passata: sono i due
    modi in cui la domanda viene posta davvero ("quanto sono 100 dollari in
    euro?", "quanto valeva il dollaro nel 2020?").
    """

    def __init__(self):
        self.session = requests.Session()
        # sessione HTTP persistente: riutilizza la connessione TCP tra chiamate

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """valida una data 'AAAA-MM-GG' proveniente dal llm; None se inutilizzabile."""
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            logger.warning("data non valida ignorata: %r", value)
            return None
        if parsed < FIRST_AVAILABLE_DATE:
            return None
        # una data futura non ha un fixing: si ricade sull'ultimo disponibile
        return min(parsed, date.today())

    @staticmethod
    def _parse_amount(value: Any) -> float:
        """importo da convertire; 1.0 se assente o non valido."""
        if value is None:
            return 1.0
        try:
            amount = float(value)
        except (TypeError, ValueError):
            logger.warning("importo non valido ignorato: %r", value)
            return 1.0
        return amount if amount > 0 else 1.0

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Chiama frankfurter per il tasso di cambio fra due valute.

        Args:
            params: "from_currency", "to_currency" e, opzionali, "amount"
                (importo da convertire) e "date" ('AAAA-MM-GG', tasso storico).

        Returns:
            dizionario con tasso e importo convertito, oppure con chiave "error".
        """
        # frankfurter usa codici maiuscoli sia nella query sia nelle chiavi di "rates":
        # il llm può estrarli minuscoli, quindi normalizziamo subito
        from_currency = params.get("from_currency", "").strip().upper()
        if not from_currency:
            return {"error": "Nessuna valuta iniziale specificata nella domanda."}

        to_currency = params.get("to_currency", "").strip().upper()
        if not to_currency:
            return {"error": "Nessuna valuta finale specificata nella domanda."}

        amount = self._parse_amount(params.get("amount"))
        wanted_date = self._parse_date(params.get("date"))

        if from_currency == to_currency:
            return {
                "provider": "frankfurter",
                "amount": amount,
                "base": from_currency,
                "quote": to_currency,
                "rates": 1.0,
                "converted": round(amount, 2),
                "date": (wanted_date or date.today()).isoformat(),
            }

        # con una data si interroga quel fixing, altrimenti l'ultimo pubblicato
        path = wanted_date.isoformat() if wanted_date else "latest"
        url = f"{settings.frankfurter_base_url.rstrip('/')}/{path}"

        try:
            res = self.session.get(
                url,
                # si chiede il tasso unitario e si moltiplica qui: l'api arrotonda
                # l'importo convertito a 2 decimali, perdendo la precisione del tasso
                params={"from": from_currency, "to": to_currency},
                timeout=20,
            )

            if res.status_code == 404 and wanted_date:
                return {"error": f"Nessun tasso disponibile per il {wanted_date.isoformat()}."}

            res.raise_for_status()
            data = res.json()
            rate = data["rates"][to_currency]

            result = {
                "provider": "frankfurter",
                "amount": amount,
                "base": data["base"],
                "quote": to_currency,
                "rates": rate,
                "converted": round(amount * rate, 2),
                "date": data["date"],
            }

            # nei giorni senza fixing frankfurter risponde con l'ultimo pubblicato:
            # requested_date conserva la data chiesta
            if wanted_date and data["date"] != wanted_date.isoformat():
                result["requested_date"] = wanted_date.isoformat()

            return result

        except Exception as err:
            logger.warning("fetch cambio valuta fallito: %s", err)
            return {"error": f"Errore nel recupero dei dati per il cambio valuta: {err}"}
