from __future__ import annotations

import httpx

from app.analysis.model_gateway import ModelGatewayError
from app.analysis.result_sanitizer import sanitize_error_text


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
    ) -> str:
        if self.wire_api == "responses":
            return self._generate_with_responses_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        if self.wire_api != "chat_completions":
            raise ModelGatewayError(f"不支持的模型 wire API：{self.wire_api}")

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        data = self._post_json(url, payload)
        choices = data.get("choices")
        if not choices:
            raise ModelGatewayError("模型接口未返回 choices")

        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelGatewayError("模型接口未返回有效文本内容")

        return content

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


def _compact_error_response(response_text: str, *, max_length: int = 220) -> str:
    text = sanitize_error_text(response_text)
    if not text:
        return "无响应正文"
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."
