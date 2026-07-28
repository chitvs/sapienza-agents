# Text2SPARQL

import requests
from translators.base_translator import BaseTranslator

class SPARQLTranslator(BaseTranslator):

    # al momento in locale, chiaramente da lanciare con docker
    # per lanciare su http://localhost:11434:
    # ollama serve
    # ollama run llama3.2
    def __init__(self, model_name: str = "llama3.2", host: str = "http://localhost:11434"):
        self.model_name = model_name
        self.host = host.rstrip("/")
        self.session = requests.Session()

    def translate(self, question: str, schema_context: str = "") -> str:

        system_prompt = (
            "Sei un esperto di Wikidata e SPARQL.\n"
            "Il tuo compito è convertire la domanda dell'utente in una query SPARQL valida per Wikidata.\n\n"
            "Principi di generazione:\n"
            "- Basati sull'evidenza: usa esclusivamente gli ID (wd:Q... e wdt:P...) forniti nel contesto. Non inventare ID.\n"
            "- Complessità minima: costruisci la query più semplice e pulita possibile.\n"
            "- Nessun filtro superfluo: aggiungi filtri (es. LANG) solo se necessari o richiesti dalla domanda.\n"
            "- Prefissi standard: usa `wd:` per le entità e `wdt:` per le proprietà.\n\n"
            "Formato di output:\n"
            "Restituisci esclusivamente il codice della query SPARQL pura. no markdown (niente ```sparql), no spiegazioni."
        )

        user_content = f"Domanda: {question}\n\nEvidenze/Contesto:\n{schema_context}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }

        response = self.session.post(f"{self.host}/api/chat", json=payload, timeout=60.0)
        response.raise_for_status()

        raw_output = response.json().get("message", {}).get("content", "").strip()
        
        # pulizia eventuale del codice
        query = raw_output.replace("```sparql", "").replace("```", "").strip()
        return query
