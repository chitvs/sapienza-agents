import logging
import re
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

class OllamaClient:
    """client di comunicazione verso il server ollama per l'esecuzione di llm locali."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model_name: str = "qwen2.5-coder:7b",
        prompts_dir: Path | str | None = None,
        timeout: float = 300.0,
        num_ctx: int = 8192,
    ):
        self.host = (host or "http://localhost:11434").rstrip("/")
        self.model_name = model_name or "qwen2.5-coder:7b"
        self.timeout = timeout
        self.num_ctx = num_ctx

        if prompts_dir is not None:
            self.prompts_dir = Path(prompts_dir)
        else:
            base_dir = Path(__file__).resolve().parent.parent
            candidate = base_dir / "agents" / "kg" / "src" / "configs" / "prompts"
            self.prompts_dir = candidate if candidate.exists() else None

        self.session = requests.Session()

    @staticmethod
    def clean_code_block(raw_output: str) -> str:
        """rimuove i blocchi di codice markdown (```sparql ... ``` o ```json ... ```) dall'output del modello."""
        if not raw_output:
            return ""

        cleaned = raw_output.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:sparql|cypher|json|sql)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
            match = re.search(r"```(?:sparql|cypher|json|sql)?\s*(.*)", cleaned, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        select_match = re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b.*", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if select_match:
            return select_match.group(0).strip()

        return cleaned

    def load_prompt(self, prompt_filename: str, **kwargs) -> str:
        """Sostituisce i soli placeholder {nome} passati come kwargs: str.format() romperebbe
        le graffe letterali negli esempi SPARQL e JSON contenuti nei prompt."""
        if not self.prompts_dir:
            raise ValueError("prompts_dir non è stato configurato.")

        prompt_path = self.prompts_dir / prompt_filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"file prompt non trovato: {prompt_path}")

        template = prompt_path.read_text(encoding="utf-8")
        for key, value in kwargs.items():
            template = template.replace("{" + key + "}", str(value))
        return template

    def chat(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.0,
        top_p: float | None = None,
    ) -> str:
        """invia messaggi di chat al modello ollama con un prompt di sistema."""
        url = f"{self.host}/api/chat"
        options: dict = {"temperature": temperature, "num_ctx": self.num_ctx}
        # ollama applica comunque il proprio top_p di default (0.9): lo si invia solo
        # quando è richiesto esplicitamente, per non fissare un valore anche a temperatura 0
        if top_p is not None:
            options["top_p"] = top_p
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": options,
        }

        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        msg = response.json().get("message", {})
        return msg.get("content", "")
