FROM python:3.14-slim

WORKDIR /app

# libgomp1: richiesta a runtime da faiss e torch (OpenMP), assente sulle immagini slim.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# torch va installato PRIMA delle altre dipendenze e dall'index CPU-only: la build di
# default su PyPI si porta dietro ~2.7 GB di librerie CUDA che il container non può
# comunque usare, non avendo accesso alla GPU. Installandolo per primo, sentence-transformers
# e gliner lo trovano già soddisfatto e non ne scaricano la variante CUDA.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# il build context è la root del monorepo (vedi docker-compose.yml): serve per copiare
# anche shared/, che vive fuori da agents/kg e non sarebbe raggiungibile altrimenti.
COPY agents/kg/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY agents/kg/src ./src

ENV PYTHONPATH=/app/src:/app

EXPOSE 8000

# start-period generoso: uvicorn non risponde finché il precaricamento dei modelli non
# è finito, e al primo avvio quel passaggio li scarica da huggingface. Il compose
# ridefinisce comunque questo healthcheck: qui il valore serve a chi usa l'immagine da sola.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
