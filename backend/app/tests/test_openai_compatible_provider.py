from app.analysis.providers.openai_compatible import _extract_responses_output_text


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
