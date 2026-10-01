from core.memory import MemoryStore


def test_memory_store_can_save_list_search_and_format(tmp_path):
    database = tmp_path / "memory.db"
    memory = MemoryStore(database)

    memory.init()
    memory.save("manual", "Jag föredrar modulär kod.")

    rows = memory.get_all()

    assert len(rows) == 1
    assert rows[0][1] == "manual"
    assert rows[0][2] == "Jag föredrar modulär kod."

    results = memory.search("Vad vet du om modulär kod?")

    assert len(results) == 1
    assert "modulär kod" in results[0][2]

    formatted = memory.format(results)

    assert "[manual]" in formatted
    assert "modulär kod" in formatted


def test_memory_store_rejects_empty_memory(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db")
    memory.init()

    try:
        memory.save("manual", "   ")
    except ValueError as error:
        assert "tomt" in str(error)
    else:
        raise AssertionError("Tomt minne ska ge ValueError")
