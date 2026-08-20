from app.analysis.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _extract_responses_output_text,
)


def test_chat_completions_enables_deepseek_max_thinking(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model_name="deepseek-v4-pro",
        reasoning_effort="max",
    )

    def fake_post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    monkeypatch.setattr(provider, "_post_json", fake_post_json)

    assert (
        provider.generate_text(
            system_prompt="Return JSON.",
            user_prompt="Confirm configuration.",
            temperature=0,
        )
        == '{"ok":true}'
    )
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"


def test_extract_responses_output_text_prefers_output_text() -> None:
    assert (
        _extract_responses_output_text(
            {
                "output_text": '{"queries":["贵州茅台 白酒政策"]}',
                "output": [],
            }
        )
        == '{"queries":["贵州茅台 白酒政策"]}'
    )


def test_extract_responses_output_text_reads_message_content() -> None:
    assert (
        _extract_responses_output_text(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"evidences":[]}',
                            }
                        ],
                    }
                ]
            }
        )
        == '{"evidences":[]}'
    )


def test_chat_completions_executes_web_search_tool(monkeypatch) -> None:
    payloads: list[dict[str, object]] = []
    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model_name="deepseek-v4-pro",
        reasoning_effort="max",
    )

    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_content": "需要补充行业信息",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": '{"query":"白酒行业渠道库存"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": '{"ok":true}'}}]},
        ]
    )

    def fake_post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
        payloads.append(payload)
        return next(responses)

    monkeypatch.setattr(provider, "_post_json", fake_post_json)
    monkeypatch.setattr(
        "app.analysis.web_search_tool.execute_web_search",
        lambda query: {"query": query, "results": [{"title": "行业库存观察"}]},
    )

    result = provider.generate_text(
        system_prompt="Return JSON.",
        user_prompt="Analyze the company.",
        temperature=0.2,
        enable_web_search=True,
    )

    assert result == '{"ok":true}'
    assert payloads[0]["tool_choice"] == "auto"
    assert payloads[0]["tools"][0]["function"]["name"] == "web_search"
    second_messages = payloads[1]["messages"]
    assert second_messages[-2]["reasoning_content"] == "需要补充行业信息"
    assert second_messages[-1]["role"] == "tool"
    assert "行业库存观察" in second_messages[-1]["content"]
