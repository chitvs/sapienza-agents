import logging
import requests
from typing import Any
from configs.settings import settings

logger = logging.getLogger(__name__)




class ExchangeProvider:
    """provider di cambio valute basato su frankfurter.app (nessuna api key necessaria)."""

    def __init__(self):
        self.session = requests.Session()
        # sessione HTTP persistente: riutilizza la connessione TCP tra chiamate

        

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Chiama l'API di frankfurter per ottenere il tasso di cambio attuale tra 2 valute.
        
        """
        from_currency = params.get("from_currency", "")
        if not from_currency:
            return {"error": "Nessuna valuta iniziale specificata nella domanda."}

        to_currency = params.get("to_currency", "")
        if not to_currency:
            return {"error": "Nessuna valuta finale specificata nella domanda."}

        if from_currency.upper() == to_currency.upper():
            return {"provider": "frankfurter", "amount": 1.0, "base": from_currency, "date": "...", "rates": 1.0}
        
        try:
            res = self.session.get(
                f"{settings.frankfurter_base_url}/latest",
                params={"from": from_currency, "to": to_currency},
                timeout=20,
            )
            res.raise_for_status()
            data = res.json()

            return {
                "provider": "frankfurter",
                "amount": data["amount"],
                "base": data["base"],
                "date":data["date"],
                "rates": data["rates"][to_currency]
            }
        except Exception as err:
            logger.warning("fetch cambio valuta fallito: %s", err)
            return {"error": f"Errore nel recupero dei dati per il cambio valuta: {err}"}
