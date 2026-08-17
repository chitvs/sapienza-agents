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

_OPENAI_COMPATIBLE_TIMEOUT: float = 30.0

class LLMClient:
    """
    Gestisce la comunicazione con i provider LLM (Gemini e Ollama), 
    fornendo metodi per la generazione di testo e l'estrazione di JSON.
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Inizializza la pipeline e il client LLM sottostante.

        Args:
            verbose (bool): Se True, abilita la stampa a schermo dei log e dei passaggi.
        """
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
        Prova il provider configurato (gemini, una chiave di settings.openai_providers,
        oppure ollama); se il provider primario è remoto e fallisce, ripiega su 'ollama'.

        Args:
            prompt (str): Il testo del prompt da inviare.
            temperature (float): La temperatura di campionamento (default: 0.0 per determinismo).
            json_mode (bool): Se True, forza l'output nel formato JSON.

        Returns:
            str: Il testo generato dal modello LLM.
        """
        provider: str = settings.llm_provider.lower()

        if provider == "ollama":
            return await self._generate_ollama(prompt, temperature, json_mode)

        try:
            if provider == "gemini":
                return await self._generate_gemini(prompt, temperature, json_mode)

            provider_config = settings.openai_providers.get(provider)
            if provider_config is None:
                raise ValueError(
                    f"provider '{provider}' non riconosciuto: non è 'gemini'/'ollama' "
                    "né una chiave presente in openai_providers"
                )

            return await self._generate_openai_compatible(
                prompt,
                temperature,
                json_mode,
                base_url=provider_config.get("base_url", ""),
                api_key=provider_config.get("api_key", ""),
                model=provider_config.get("model", ""),
            )
        except Exception as err:
            if not settings.enable_local_fallback:
                self._log(
                    f"  [error] {provider} non disponibile, fallback disattivato. Errore: {err}",
                    level=logging.ERROR
                )
                raise err
                
            self._log(
                f"  [warn] {provider} non disponibile ({err.__class__.__name__}: {err}), fallback su ollama",
                level=logging.WARNING,
            )
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
    

    async def _generate_openai_compatible(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        base_url: str,
        api_key: str,
        model: str,
    ) -> str:
        """
        Chiama un endpoint compatibile con l'API chat/completions di OpenAI
        (es. OpenRouter) tramite HTTPX.

        Args:
            prompt (str): Il testo del prompt da inviare.
            temperature (float): La temperatura di campionamento.
            json_mode (bool): Se True, richiede output JSON via response_format.
            base_url (str): URL base dell'endpoint (es. https://openrouter.ai/api/v1).
            api_key (str): Chiave API per l'autenticazione Bearer.
            model (str): Nome del modello da invocare presso questo provider.

        Returns:
            str: La risposta testuale del modello.

        Raises:
            ValueError: Se base_url, api_key o model sono mancanti.
            httpx.HTTPError: Se c'è un problema di rete o l'API risponde con un errore.
        """
        if not base_url or not api_key or not model:
            raise ValueError("configurazione provider incompleta: servono base_url, api_key e model")

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        client = get_http_client()
        resp = await client.post(url, headers=headers, json=payload, timeout=_OPENAI_COMPATIBLE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            self._log("  [warn] openai-compatible: nessuna choice nella risposta", level=logging.WARNING)
            return ""

        return choices[0].get("message", {}).get("content", "").strip()

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
            "think": False,
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