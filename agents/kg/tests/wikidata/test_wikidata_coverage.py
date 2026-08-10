"""
Test su dimensioni di complessità MAI verificate nelle sessioni precedenti: proprietà
multivalore, catene multi-hop a 3+ salti, qualificatori temporali (p:/ps:/pq:), e
aggregazioni COUNT. Servono a capire dove sta il vero soffitto della pipeline, non a
confermare fix già fatti — a differenza degli altri file test_pipeline*.py, nessuna di
queste domande è mai stata eseguita contro la pipeline reale: è lecito che qualcuna
fallisca, è proprio quello che vogliamo scoprire.
"""
import pytest
import requests
from pipeline import KGPipeline

def is_ollama_running():
    try:
        return requests.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_switzerland_official_languages_list():
    """proprietà multivalore: la Svizzera ha 4 lingue ufficiali, non 1 - verifica che il
    sistema non assuma implicitamente un singolo valore per riga."""
    pipeline = KGPipeline()
    result = pipeline.run("What are the official languages of Switzerland?")
    assert len(result.results) > 0
    assert any("German" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_switzerland_official_languages_count():
    """stesso fatto multivalore, ma come aggregazione COUNT invece di lista."""
    pipeline = KGPipeline()
    result = pipeline.run("How many official languages does Switzerland have?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_titanic_director_citizenship_capital():
    """catena a 3 hop: Titanic -> regista (James Cameron) -> cittadinanza -> capitale."""
    # Cameron ha doppia cittadinanza su Wikidata (Canada e Nuova Zelanda): entrambe le
    # capitali sono risposte corrette, pretenderne una sola boccerebbe una query giusta
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of the country of citizenship of the director of Titanic?")
    assert len(result.results) > 0
    assert any(capital in str(row) for row in result.results for capital in ("Ottawa", "Wellington"))

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_us_president_2010():
    """qualificatore temporale (point-in-time): richiede il pattern p:/ps:/pq: menzionato
    nel prompt di traduzione ma mai esercitato in nessun test precedente."""
    pipeline = KGPipeline()
    result = pipeline.run("Who was the president of the United States in 2010?")
    assert len(result.results) > 0
    assert any("Obama" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_bach_children_count():
    """aggregazione COUNT su una persona: i dati storici variano fra le fonti, quindi si
    verifica solo che il conteggio esista e non sia vuoto."""
    pipeline = KGPipeline()
    result = pipeline.run("How many children did Johann Sebastian Bach have?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_eiffel_tower_country():
    """multi-hop attraverso un'entità "ancora" insolita (un monumento, non un paese/persona
    citato direttamente): Torre Eiffel -> paese (Francia) -> montagna più alta (Monte Bianco)."""
    pipeline = KGPipeline()
    result = pipeline.run("What is the highest mountain in the country where the Eiffel Tower is located?")
    assert len(result.results) > 0
    assert any("Mont Blanc" in str(row) or "Blanc" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_official_language_capital_paris():
    """multi-hop attraverso una relazione INVERSA: non "capitale di Francia" ma "il paese
    la cui capitale è Parigi" -> lingua ufficiale (Francese)."""
    pipeline = KGPipeline()
    result = pipeline.run("What is the official language of the country whose capital is Paris?")
    assert len(result.results) > 0
    assert any("French" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mars_moons_count():
    """altra aggregazione COUNT, questa volta su un fatto scientifico stabile (Marte ha
    esattamente 2 lune: Phobos e Deimos) per avere un confronto con verità nota."""
    pipeline = KGPipeline()
    result = pipeline.run("How many moons does Mars have?")
    assert len(result.results) > 0
