from __future__ import annotations

import json

import httpx

from app.analysis.model_gateway import ModelGatewayError
from app.analysis.result_sanitizer import sanitize_error_text

MAX_WEB_SEARCH_ROUNDS = 3
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索互联网中的公开基本面信息。在现有财务、公告和外部证据不足以回答"
            "分析问题时使用；不要搜索行情、目标价、评级或交易建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "简洁、具体、适合网页搜索的查询词。",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        wire_api: str = "chat_completions",
        reasoning_effort: str | None = None,
        disable_response_storage: bool = False,
        timeout: float = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.wire_api = wire_api
        self.reasoning_effort = reasoning_effort
        self.disable_response_storage = disable_response_storage
        self.timeout = timeout

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        enable_web_search: bool = False,
    ) -> str:
        if enable_web_search and self.wire_api != "chat_completions":
            raise ModelGatewayError("当前只有 Chat Completions 接口支持分析师网页搜索")
        if self.wire_api == "responses":
            return self._generate_with_responses_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        if self.wire_api != "chat_completions":
            raise ModelGatewayError(f"不支持的模型 wire API：{self.wire_api}")

        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if enable_web_search:
            return self._generate_with_web_search(
                messages=messages,
                temperature=temperature,
            )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        self._apply_reasoning_options(payload)
        message = self._post_chat_completion(payload)
        return _message_content(message)

    def _generate_with_web_search(
        self,
        *,
        messages: list[dict[str, object]],
        temperature: float,
    ) -> str:
        for _ in range(MAX_WEB_SEARCH_ROUNDS):
            payload: dict[str, object] = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "tools": [WEB_SEARCH_TOOL],
                "tool_choice": "auto",
            }
            self._apply_reasoning_options(payload)
            message = self._post_chat_completion(payload)
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                return _message_content(message)

            messages.append(_assistant_tool_call_message(message))
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                messages.append(_execute_tool_call(tool_call))

        final_payload: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "tools": [WEB_SEARCH_TOOL],
            "tool_choice": "none",
        }
        self._apply_reasoning_options(final_payload)
        return _message_content(self._post_chat_completion(final_payload))

    def _post_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        data = self._post_json(f"{self.base_url}/chat/completions", payload)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelGatewayError("模型接口未返回 choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ModelGatewayError("模型接口返回的 choice 结构异常")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ModelGatewayError("模型接口未返回有效 message")
        return message

    def _apply_reasoning_options(self, payload: dict[str, object]) -> None:
        if not self.reasoning_effort:
            return
        if self.model_name.startswith("deepseek-"):
            payload["thinking"] = {
                "type": "disabled" if self.reasoning_effort == "none" else "enabled"
            }
            if self.reasoning_effort != "none":
                payload["reasoning_effort"] = self.reasoning_effort
            return
        payload["reasoning_effort"] = self.reasoning_effort

    def _generate_with_responses_api(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload: dict[str, object] = {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "text": {"format": {"type": "json_object"}},
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.disable_response_storage:
            payload["store"] = False

        data = self._post_json(f"{self.base_url}/responses", payload)
        return _extract_responses_output_text(data)

    def _post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = _compact_error_response(exc.response.text)
            raise ModelGatewayError(
                f"模型接口返回错误：HTTP {exc.response.status_code}；{response_text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelGatewayError(f"模型接口请求失败：{exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ModelGatewayError("模型接口未返回 JSON 响应") from exc
        if not isinstance(data, dict):
            raise ModelGatewayError("模型接口返回的 JSON 结构异常")
        return data


def _extract_responses_output_text(data: dict[str, object]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    return text

    raise ModelGatewayError("Responses API 未返回有效文本内容")


def _message_content(message: dict[str, object]) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ModelGatewayError("模型接口未返回有效文本内容")
    return content


def _assistant_tool_call_message(message: dict[str, object]) -> dict[str, object]:
    forwarded: dict[str, object] = {
        "role": "assistant",
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls"),
    }
    reasoning_content = message.get("reasoning_content")
    if reasoning_content is not None:
        forwarded["reasoning_content"] = reasoning_content
    return forwarded


def _execute_tool_call(tool_call: dict[str, object]) -> dict[str, object]:
    call_id = str(tool_call.get("id") or "")
    function = tool_call.get("function")
    function = function if isinstance(function, dict) else {}
    function_name = str(function.get("name") or "")
    raw_arguments = function.get("arguments")

    try:
        if function_name != "web_search":
            raise ValueError(f"不支持的工具：{function_name or 'unknown'}")
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else {}
        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("web_search.query 不能为空")

        from app.analysis.web_search_tool import execute_web_search

        result = execute_web_search(query)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"error": sanitize_error_text(str(exc))}
    except Exception as exc:
        result = {"error": f"网页搜索暂时不可用：{sanitize_error_text(str(exc))}"}

    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(result, ensure_ascii=False, default=str),
    }


def _compact_error_response(response_text: str, *, max_length: int = 220) -> str:
    text = sanitize_error_text(response_text)
    if not text:
        return "无响应正文"
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."
