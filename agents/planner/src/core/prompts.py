"""Caricamento e rendering dei template di prompt usati dal Planner."""

from pathlib import Path
from typing import Any

from configs.settings import settings
from clients.llm_client import LLMClient


class PromptLibrary:
    """Carica i template di prompt da disco (con cache in memoria) e li esegue
    contro un LLMClient, restituendo il JSON estratto dalla risposta."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """Inizializza la libreria.

        Args:
            prompts_dir: Cartella contenente i template. Se None, usa settings.prompts_dir.
        """
        self._dir = prompts_dir or settings.prompts_dir
        self._cache: dict[str, str] = {}

    def _load(self, filename: str) -> str:
        """Carica un template dalla cartella prompts, con cache in memoria.

        Args:
            filename: Il nome del file (es. 'draft_study.txt').

        Returns:
            Il contenuto testuale del template.
        """
        if filename not in self._cache:
            self._cache[filename] = (self._dir / filename).read_text(encoding="utf-8")
        return self._cache[filename]

    async def extract_json(self, filename: str, llm: LLMClient, **format_kwargs: Any) -> dict[str, Any] | None:
        """Carica un template, lo formatta con i kwarg forniti e ne estrae il
        JSON dalla risposta del modello.

        Args:
            filename: Il nome del file di prompt da caricare.
            llm: Il client LLM da interrogare.
            **format_kwargs: Variabili per formattare il template testuale.

        Returns:
            Il JSON estratto come dizionario, o None in caso di errore.
        """
        template = self._load(filename)
        prompt = template.format(**format_kwargs)
        return await llm.extract_json(prompt)