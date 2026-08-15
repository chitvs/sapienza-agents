"""
Client LLM del planner: gestisce la comunicazione con i provider (Gemini o Ollama).

Si occupa esclusivamente del trasporto della richiesta verso il modello e della
pulizia iniziale della risposta grezza (estrazione JSON). Non contiene logica
di business, validazione o retry semantici, i quali sono delegati alla pipeline.
"""

import json
import logging
import re
from typing import Any

from configs.settings import settings
from http_client import get_http_client

logger = logging.getLogger("planner_llm_client")


class LLMClient:
    """
    Gestisce la comunicazione con i provider LLM (Gemini e Ollama), 
    fornendo metodi per la generazione di testo e l'estrazione di JSON.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose: bool = verbose

    def _log(self, msg: str, level: int = logging.INFO) -> None:
        """
        Gestisce il logging interno della classe.

        Args:
            msg (str): Il messaggio da registrare.
            level (int): Il livello di severità del log (default: logging.INFO).
        """
        if self.verbose:
            # Stampa a schermo per debug rapido se verbose è True
            print(msg)

        # Usa il livello semantico corretto invece di forzare sempre .info()
        logger.log(level, msg)

    async def generate(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """
        Prova il provider configurato; se è impostato su 'gemini' e fallisce, ripiega su 'ollama'.

        Args:
            prompt (str): Il testo del prompt da inviare.
            temperature (float): La temperatura di campionamento (default: 0.0 per determinismo).
            json_mode (bool): Se True, forza l'output nel formato JSON.

        Returns:
            str: Il testo generato dal modello LLM.
        """
        if settings.llm_provider.lower() == "gemini":
            try:
                return await self._generate_gemini(prompt, temperature, json_mode)
            except Exception as err:
                # Il fallback cattura l'errore senza crashare e riprova in locale
                self._log(
                    f"  [warn] gemini non disponibile ({err.__class__.__name__}: {err}), fallback su ollama",
                    level=logging.WARNING,
                )
                return await self._generate_ollama(prompt, temperature, json_mode)
        
        return await self._generate_ollama(prompt, temperature, json_mode)

    async def _generate_gemini(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """
        Chiama l'API di Google Gemini tramite HTTPX.

        Args:
            prompt (str): Il testo del prompt da inviare.
            temperature (float): La temperatura di campionamento.
            json_mode (bool): Se True, imposta il mime_type su application/json.

        Returns:
            str: La risposta testuale di Gemini.

        Raises:
            ValueError: Se la chiave API di Gemini manca.
            httpx.HTTPError: Se c'è un problema di rete o l'API risponde con un errore.
        """
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY non configurata")

        url = f"{settings.gemini_api_base}/models/{settings.gemini_model}:generateContent"
        headers = {"x-goog-api-key": settings.gemini_api_key}

        generation_config: dict[str, Any] = {}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        
        generation_config["temperature"] = temperature

        payload: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
        if generation_config:
            payload["generationConfig"] = generation_config

        client = get_http_client()
        resp = await client.post(url, headers=headers, json=payload, timeout=settings.gemini_timeout)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            # Gestiamo il caso in cui Gemini censuri la risposta o la blocchi per policy
            block_reason = data.get("promptFeedback", {}).get("blockReason")
            self._log(
                f"  [warn] gemini: nessuna candidate, blockReason={block_reason!r}",
                level=logging.WARNING,
            )
            return ""

        parts = candidates[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "").strip() if parts else ""

    async def _generate_ollama(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """
        Chiama l'API locale di Ollama tramite HTTPX.

        Args:
            prompt (str): Il testo del prompt da inviare.
            temperature (float): La temperatura di campionamento.
            json_mode (bool): Se True, imposta il flag 'format'='json'.

        Returns:
            str: La risposta testuale di Ollama.

        Raises:
            httpx.HTTPError: Se il servizio Ollama non è raggiungibile o risponde con errore.
        """
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        client = get_http_client()
        resp = await client.post(url, json=payload, timeout=settings.ollama_timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    @staticmethod
    def clean_json(raw: str) -> str:
        """
        Pulisce la stringa restituita dal modello, rimuovendo eventuali formattazioni
        Markdown come i blocchi di codice (```json ... ```) per estrarre il payload puro.

        Args:
            raw (str): La stringa grezza generata dall'LLM.

        Returns:
            str: La stringa pulita pronta per essere elaborata da json.loads().
        """
        if not raw:
            return ""
        
        cleaned: str = raw.strip()
        if "```" in cleaned:
            # Cerca un blocco di codice markdown (opzionalmente etichettato con 'json').
            # re.DOTALL permette al punto (.*?) di matchare anche i newline (\n).
            match = re.search(
                r"```(?:json)?\s*(.*?)\s*```", 
                cleaned, 
                flags=re.IGNORECASE | re.DOTALL
            )
            if match:
                return match.group(1).strip()
                
        return cleaned

    async def extract_json(self, prompt: str) -> dict[str, Any] | None:
        """
        Invia un prompt all'LLM e tenta di effettuare il parsing della risposta come JSON.

        Args:
            prompt (str): Il testo del prompt da inviare.

        Returns:
            dict[str, Any] | None: Il dizionario parsato se il JSON è valido, 
            altrimenti None. Non solleva eccezioni di parsing.
        """
        raw: str = await self.generate(prompt, json_mode=True)
        cleaned: str = self.clean_json(raw)
        
        self._log(f"  -> risposta llm grezza: {raw}")
        
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log(
                f"  [warn] impossibile parsare json: {cleaned}", 
                level=logging.WARNING
            )
            return None