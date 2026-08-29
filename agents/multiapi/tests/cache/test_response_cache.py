import time

from cache.response_cache import ResponseCache


def test_cache_hit():
    cache = ResponseCache(capacity=5)
    cache.set("Che tempo fa a Roma?", "weather", [{"temperature_c": 25}])
    result = cache.get("che tempo fa a roma?")
    assert result is not None
    assert result["intent"] == "weather"
    assert result["results"][0]["temperature_c"] == 25


def test_cache_miss():
    cache = ResponseCache(capacity=5)
    assert cache.get("Domanda non presente") is None


def test_cache_normalization():
    """la cache deve ignorare maiuscole, punteggiatura e spazi multipli."""
    cache = ResponseCache(capacity=5)
    cache.set("Che tempo fa a Roma??!", "weather", [{"temp": 25}])
    result = cache.get("  CHE  TEMPO FA  A  ROMA  ")
    assert result is not None
    assert result["intent"] == "weather"


def test_cache_eviction_fifo():
    """quando la cache è piena, il primo elemento inserito viene rimosso."""
    cache = ResponseCache(capacity=2)
    cache.set("domanda 1", "weather", [{"a": 1}])
    cache.set("domanda 2", "exchange_rate", [{"b": 2}])
    # inserire un terzo elemento deve rimuovere il primo (FIFO)
    cache.set("domanda 3", "weather", [{"c": 3}])
    assert cache.get("domanda 1") is None
    assert cache.get("domanda 2") is not None
    assert cache.get("domanda 3") is not None


def test_cache_update_existing():
    """aggiornare una domanda già in cache non deve causare eviction."""
    cache = ResponseCache(capacity=2)
    cache.set("domanda 1", "weather", [{"a": 1}])
    cache.set("domanda 2", "exchange_rate", [{"b": 2}])
    # aggiornare domanda 1 non deve rimuovere domanda 2
    cache.set("domanda 1", "weather", [{"a": 999}])
    assert cache.get("domanda 1")["results"][0]["a"] == 999
    assert cache.get("domanda 2") is not None


def test_cache_clear():
    cache = ResponseCache(capacity=5)
    cache.set("test", "weather", [{"x": 1}])
    cache.clear()
    assert cache.get("test") is None


def test_cache_entry_expires():
    """una voce scaduta non deve essere restituita."""
    cache = ResponseCache(capacity=5)
    cache.set("domanda", "weather", [{"a": 1}], ttl=0.05)
    assert cache.get("domanda") is not None
    time.sleep(0.1)
    assert cache.get("domanda") is None


def test_cache_ttl_zero_non_memorizza():
    """ttl 0 = dato troppo volatile: non deve entrare in cache."""
    cache = ResponseCache(capacity=5)
    cache.set("che ore sono a tokyo", "time_info", [{"time": "04:39:12"}], ttl=0)
    assert cache.get("che ore sono a tokyo") is None


def test_cache_default_ttl_dal_costruttore():
    """senza ttl esplicito vale quello del costruttore."""
    cache = ResponseCache(capacity=5, default_ttl=0.05)
    cache.set("domanda", "weather", [{"a": 1}])
    assert cache.get("domanda") is not None
    time.sleep(0.1)
    assert cache.get("domanda") is None


def test_eviction_non_sacrifica_voci_valide():
    """le voci scadute vengono rimosse prima di sfrattare quelle ancora valide."""
    cache = ResponseCache(capacity=2)
    cache.set("scaduta", "weather", [{"a": 1}], ttl=0.05)
    cache.set("viva", "weather", [{"b": 2}], ttl=60)
    time.sleep(0.1)
    cache.set("nuova", "weather", [{"c": 3}], ttl=60)
    assert cache.get("viva") is not None, "una voce valida e stata sfrattata al posto di una scaduta"
    assert cache.get("nuova") is not None
