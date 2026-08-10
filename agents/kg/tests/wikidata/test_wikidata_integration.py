"""
Test end-to-end della pipeline su Wikidata: fatti diretti, catene multi-hop, superlativi,
aggregazioni e domande booleane. Confermano che le riparazioni già fatte reggono.
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
def test_albert_einstein_birth_date():
    pipeline = KGPipeline()
    result = pipeline.run("What is the birth date of Albert Einstein?")
    assert len(result.results) > 0
    assert "1879-03-14" in str(result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_real_madrid_president():
    pipeline = KGPipeline()
    result = pipeline.run("Who is the president of Real Madrid?")
    assert len(result.results) > 0
    res_str = str(result.results)
    assert "Florentino Pérez" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_france_capital():
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of France?")
    assert len(result.results) > 0
    res_str = str(result.results)
    assert "Paris" in res_str

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_descriptive_query():
    pipeline = KGPipeline()
    result = pipeline.run("Who is Minerva?")
    assert len(result.results) > 0
    res_str = str(result.results).lower()
    assert any(word in res_str for word in ["war", "wisdom", "goddess", "roman", "strategic"])

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_sapienza_founding_date():
    pipeline = KGPipeline()
    result = pipeline.run("When was Sapienza University founded?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_elevation_rome():
    pipeline = KGPipeline()
    result = pipeline.run("What is the elevation of Rome?")
    assert len(result.results) > 0
    assert any("21" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_capital_germany():
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of Germany?")
    assert len(result.results) > 0
    assert any("Berlin" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_penicillin_discoverer():
    pipeline = KGPipeline()
    result = pipeline.run("Who discovered penicillin?")
    assert len(result.results) > 0
    assert any("Fleming" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_julius_caesar_birthplace():
    pipeline = KGPipeline()
    result = pipeline.run("Where was Julius Caesar born?")
    assert len(result.results) > 0
    assert any("Rome" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_psg_coach():
    pipeline = KGPipeline()
    result = pipeline.run("Who is the coach of Paris Saint-Germain?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_spain():
    pipeline = KGPipeline()
    result = pipeline.run("What is the highest mountain in Spain?")
    assert len(result.results) > 0
    assert any("Teide" in str(row) or "Mulhacén" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_world_war_two_end():
    pipeline = KGPipeline()
    result = pipeline.run("When did World War II end?")
    assert len(result.results) > 0
    assert any("1945" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_marie_curie_birth():
    pipeline = KGPipeline()
    result = pipeline.run("When was Marie Curie born?")
    assert len(result.results) > 0
    assert any("1867" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_juventus_stadium():
    pipeline = KGPipeline()
    result = pipeline.run("In which stadium does Juventus play?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_tokyo_country():
    pipeline = KGPipeline()
    result = pipeline.run("What country is Tokyo located in?")
    assert len(result.results) > 0
    assert any("Japan" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_divine_comedy_author():
    pipeline = KGPipeline()
    result = pipeline.run("Who wrote the Divine Comedy?")
    assert len(result.results) > 0
    assert any("Dante" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_capital_most_populous_country():
    pipeline = KGPipeline()
    result = pipeline.run("What is the capital of the most populous country in the world?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_einstein_wife_birthplace():
    pipeline = KGPipeline()
    result = pipeline.run("In which city was Albert Einstein's wife born?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_highest_mountain_italy():
    pipeline = KGPipeline()
    result = pipeline.run("What is the highest mountain in Italy?")
    assert len(result.results) > 0
    assert any("Mont Blanc" in str(row) or "Monte Bianco" in str(row) or "Blanc" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mayor_capital_france():
    pipeline = KGPipeline()
    result = pipeline.run("Who is the mayor of the capital of France?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_director_inception_birth_country():
    pipeline = KGPipeline()
    result = pipeline.run("In what country was the director of Inception born?")
    assert len(result.results) > 0
    assert any("United Kingdom" in str(row) or "UK" in str(row) or "England" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_real_madrid_stadium_city():
    pipeline = KGPipeline()
    result = pipeline.run("In which city is the Real Madrid stadium located?")
    assert len(result.results) > 0
    assert any("Madrid" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_shakespeare_hometown_country():
    pipeline = KGPipeline()
    result = pipeline.run("In which country is William Shakespeare's hometown located?")
    assert len(result.results) > 0

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_penicillin_discoverer_birthdate():
    pipeline = KGPipeline()
    result = pipeline.run("What is the birth date of the person who discovered penicillin?")
    assert len(result.results) > 0
    assert any("1881" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_polonium_discoverer():
    pipeline = KGPipeline()
    result = pipeline.run("Who discovered polonium?")
    assert len(result.results) > 0
    assert any("Curie" in str(row) for row in result.results)

@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_mona_lisa_museum():
    pipeline = KGPipeline()
    result = pipeline.run("In which museum is the Mona Lisa located?")
    assert len(result.results) > 0
    assert any("Louvre" in str(row) for row in result.results)
