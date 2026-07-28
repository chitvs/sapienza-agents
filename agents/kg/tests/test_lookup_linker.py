from linkers.lookup_linker import LookupLinker

def test_link():
    linker = LookupLinker()
    results = linker.link("universe")

    assert len(results) > 0
    assert results[0].qid == "Q1"
