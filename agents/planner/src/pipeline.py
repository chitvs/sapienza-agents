import json
import logging
import re
import time

import requests

from api.schemas import PlanDay, PlanDomain, QueryRequest, QueryResponse
from configs.settings import settings

logger = logging.getLogger("planner_pipeline")

# mapping dominio -> prompt di drafting specializzato (punto 3 della roadmap)
_DRAFT_PROMPTS: dict[str, str] = {
    "study": "draft_study.txt",
    "travel": "draft_travel.txt",
    "routine": "draft_routine.txt",
}


class PlannerPipeline:
    """pipeline dell'agente planner: classifica il dominio, genera una bozza del piano,
    predispone l'arricchimento e finalizza la risposta.

    Fasi: classify_domain -> draft -> enrich (placeholder) -> finalize
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._prompts_cache: dict[str, str] = {}

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    # -- llm helpers (stesso pattern di multiapi, self-contained) ----

    def _llm_generate(self, prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
        """chiama ollama /api/generate e restituisce la risposta grezza.

        json_mode attiva il vincolo nativo di ollama (`format: "json"`), che forza il
        decoding a produrre testo JSON sintatticamente valido. Va usato IN AGGIUNTA alle
        istruzioni nel prompt, non al loro posto: garantisce che l'output sia json valido,
        non che contenga i campi attesi con i tipi giusti (quello resta compito della
        validazione Pydantic a valle).
        """
        url = f"{settings.ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        resp = requests.post(url, json=payload, timeout=settings.ollama_timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    @staticmethod
    def _clean_json(raw: str) -> str:
        """rimuove eventuali blocchi markdown (```json ... ```) dalla risposta llm."""
        if not raw:
            return ""
        cleaned = raw.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return cleaned

    def _load_prompt(self, filename: str) -> str:
        """carica un template prompt dalla cartella prompts (con cache)."""
        if filename not in self._prompts_cache:
            path = settings.prompts_dir / filename
            self._prompts_cache[filename] = path.read_text(encoding="utf-8")
        return self._prompts_cache[filename]

    def _llm_extract_json(self, prompt_file: str, **format_kwargs) -> dict | None:
        """helper generico: carica un prompt, lo invia al llm, parsa il json di risposta."""
        template = self._load_prompt(prompt_file)
        prompt = template.format(**format_kwargs)
        raw = self._llm_generate(prompt, json_mode=True)
        cleaned = self._clean_json(raw)
        self._log(f"  -> risposta llm grezza: {raw}")

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError):
            self._log(f"  [warn] impossibile parsare json: {cleaned}")
            return None

    # ----- fase 1: classificazione del dominio -----

    def _classify_domain(self, request: QueryRequest) -> PlanDomain:
        if request.domain_hint is not None:
            self._log(f"[info] dominio forzato da domain_hint: {request.domain_hint}")
            return request.domain_hint

        self._log("\n[info] [step] classificazione dominio via llm")
        data = self._llm_extract_json("classify_domain.txt", question=request.question)

        domain = data.get("domain") if data else None
        if domain in ("study", "travel", "routine"):
            self._log(f"  -> dominio classificato: {domain}")
            return domain

        self._log(f"  [warn] classificazione non valida/'unknown' ({domain}), fallback a '{settings.default_domain}'")
        return settings.default_domain

    # ----- fase 2: drafting -----

    def _draft(self, request: QueryRequest, domain: PlanDomain) -> dict:
        """genera la bozza del piano via llm, con prompt specializzato per dominio."""
        self._log(f"\n[info] [step] drafting piano (dominio={domain})")
        prompt_file = _DRAFT_PROMPTS[domain]
        data = self._llm_extract_json(prompt_file, question=request.question)

        if data and "days" in data:
            return data

        self._log("  [warn] drafting fallito o incompleto, restituisco struttura vuota")
        return {"title": request.question, "days": []}

    # ----- fase 3: enrichment (placeholder) -----

    def _enrich(self, draft: dict, request: QueryRequest) -> dict:
        """placeholder per l'arricchimento con dati esterni (meteo, entità dal KG, ecc.).

        Per ora si limita a propagare l'eventuale `context` ricevuto in input dentro
        `external_data` di ogni giorno, senza alcuna chiamata reale. Da sostituire quando
        il planner (o l'orchestratore) potrà interrogare kg-agent/multiapi-agent.
        """
        if not request.context:
            return draft

        self._log("\n[info] [step] enrichment (placeholder, nessuna chiamata esterna)")
        for day in draft.get("days", []):
            day.setdefault("external_data", {})
            day["external_data"].update(request.context)
        return draft

    # ----- fase 4: finalizzazione -----

    def _finalize(self, request: QueryRequest, domain: PlanDomain, draft: dict, elapsed_ms: float) -> QueryResponse:
        days = [PlanDay(**d) for d in draft.get("days", [])]
        confidence = 1.0 if days else 0.0

        return QueryResponse(
            question=request.question,
            domain=domain,
            title=draft.get("title") or request.question,
            summary=draft.get("summary"),
            days=days,
            contingency_notes=draft.get("contingency_notes"),
            confidence=confidence,
            execution_time_ms=elapsed_ms,
        )

    # ----- entrypoint pubblico -----

    def run(self, request: QueryRequest) -> QueryResponse:
        start_time = time.time()

        domain = self._classify_domain(request)
        draft = self._draft(request, domain)
        enriched = self._enrich(draft, request)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return self._finalize(request, domain, enriched, elapsed_ms)