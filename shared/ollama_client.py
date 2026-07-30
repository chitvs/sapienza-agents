import re
from pathlib import Path
import requests
from configs.settings import settings

class OllamaClient:
    """client unificato e condiviso per interagire con le api di ollama."""

    def __init__(
        self,
        host: str | None = None,
        model_name: str | None = None,
        timeout: float | None = None,
        prompts_dir: Path | str | None = None,
    ):
        self.session = None
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model_name = model_name or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout
        self.prompts_dir = Path(prompts_dir) if prompts_dir else settings.prompts_dir
        self.session = requests.Session()

    def close(self):
        """chiude la sessione requests."""
        if hasattr(self, "session") and self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    @staticmethod
    def clean_code_block(raw_output: str) -> str:
        """rimuove i blocchi di codice markdown (```sparql, ```cypher, ```json, ```)."""
        if not raw_output:
            return ""

        cleaned = raw_output.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part_str = part.strip()
                if part_str.startswith(("sparql", "cypher", "json", "sql")):
                    part_str = re.sub(r"^(sparql|cypher|json|sql)\s*", "", part_str, flags=re.IGNORECASE).strip()
                if part_str:
                    cleaned = part_str
                    break

        cleaned = cleaned.replace("```", "").strip()
        return cleaned

    def load_prompt(self, prompt_filename: str, **kwargs) -> str:
        """carica un prompt da file e lo formatta con i parametri passati."""
        if not self.prompts_dir:
            raise ValueError("prompts_dir non è stato configurato.")

        prompt_path = self.prompts_dir / prompt_filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"File prompt non trovato: {prompt_path}")

        template = prompt_path.read_text(encoding="utf-8")
        if kwargs:
            return template.format(**kwargs)
        return template

    def generate(self, prompt: str, temperature: float = 0.0) -> str:
        """invia un prompt al modello Ollama e restituisce la risposta."""
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }

        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def chat(self, system_prompt: str, user_content: str, temperature: float = 0.0) -> str:
        """invia un messaggio chat con un system prompt al modello Ollama."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }

        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "").strip()
