"""
Client LLM del planner: dispatch gemini/ollama con fallback, pulizia della risposta
grezza ed estrazione json. Separato da pipeline.py perché è puro "trasporto" verso il
modello, senza conoscenza di dominio (prompt, validazione, retry semantico restano in
pipeline.py, dove vive quella conoscenza).

Non è un "corrector" nel senso di agents/multiapi/src/correctors/llm_response_corrector.py:
qui non c'è alcun retry, extract_json() restituisce None in caso di fallimento e lascia
decidere al chiamante (vedi _validate_and_correct in pipeline.py).
"""

import json
import logging
import re

import httpx

from configs.settings import settings

logger = logging.getLogger("planner_llm_client")


class LLMClient:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    async def generate(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """Prova il provider configurato; se è gemini e fallisce, ripiega su ollama."""
        if settings.llm_provider.lower() == "gemini":
            try:
                return await self._generate_gemini(prompt, temperature, json_mode)
            except Exception as err:
                self._log(f"  [warn] gemini non disponibile ({err.__class__.__name__}: {err}), fallback su ollama")
                return await self._generate_ollama(prompt, temperature, json_mode)
        return await self._generate_ollama(prompt, temperature, json_mode)

    async def _generate_gemini(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY non configurata")

        url = f"{settings.gemini_api_base}/models/{settings.gemini_model}:generateContent"
        headers = {"x-goog-api-key": settings.gemini_api_key}

        generation_config: dict = {}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if generation_config:
            payload["generationConfig"] = generation_config

        async with httpx.AsyncClient(timeout=settings.gemini_timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                block_reason = data.get("promptFeedback", {}).get("blockReason")
                self._log(f"  [warn] gemini: nessuna candidate, blockReason={block_reason!r}")
                return ""

            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "").strip() if parts else ""

    async def _generate_ollama(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    @staticmethod
    def clean_json(raw: str) -> str:
        if not raw:
            return ""
        cleaned = raw.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return cleaned

    async def extract_json(self, prompt: str) -> dict | None:
        raw = await self.generate(prompt, json_mode=True)
        cleaned = self.clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log(f"  [warn] impossibile parsare json: {cleaned}")
            return None