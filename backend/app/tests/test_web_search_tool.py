from app.analysis.web_search_tool import clear_web_search_cache, execute_web_search
from app.data_sources.web_search_provider import SearchResult


def test_web_search_tool_caches_identical_query(monkeypatch) -> None:
    clear_web_search_cache()
    calls: list[tuple[str, int]] = []

    def fake_search(self, query: str, limit: int = 5):
        calls.append((query, limit))
        return [
            SearchResult(
                query=query,
                title="行业公开信息",
                url="https://example.test/industry",
                source="example.test",
                snippet="行业需求保持稳定。",
            )
        ]

    monkeypatch.setattr(
        "app.analysis.web_search_tool.CompositeWebSearchProvider.search",
        fake_search,
    )

    first = execute_web_search("  白酒行业   需求  ")
    second = execute_web_search("白酒行业 需求")

    assert calls == [("白酒行业 需求", 5)]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["results"][0]["url"] == "https://example.test/industry"
