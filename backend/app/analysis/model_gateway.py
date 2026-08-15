from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelGatewayError(RuntimeError):
    pass


class ModelNotConfiguredError(ModelGatewayError):
    pass


class ModelOutputValidationError(ModelGatewayError):
    pass


class ModelGateway:
    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        wire_api: str | None = None,
        reasoning_effort: str | None = None,
        disable_response_storage: bool | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.provider = provider or settings.model_provider
        self.base_url = base_url if base_url is not None else settings.model_base_url
        self.api_key = api_key if api_key is not None else settings.model_api_key
        self.model_name = model_name if model_name is not None else settings.model_name
        self.wire_api = wire_api or settings.model_wire_api
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else settings.model_reasoning_effort
        )
        self.disable_response_storage = (
            disable_response_storage
            if disable_response_storage is not None
            else settings.model_disable_response_storage
        )
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.model_timeout_seconds
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model_name)

    def status(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "wire_api": "responses" if self.provider == "codex" else self.wire_api,
            "api_key_configured": bool(self.api_key),
        }

    def require_configured(self) -> None:
        missing = []
        if not self.base_url:
            missing.append("MODEL_BASE_URL")
        if not self.api_key:
            missing.append("MODEL_API_KEY")
        if not self.model_name:
            missing.append("MODEL_NAME")

        if missing:
            joined = ", ".join(missing)
            raise ModelNotConfiguredError(f"模型未配置，请先在 .env 中设置：{joined}")

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        temperature: float = 0.2,
    ) -> SchemaT:
        self.require_configured()
        raw_content = self._generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        return parse_model_json(raw_content, schema)

    def _generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        if self.provider not in {"openai_compatible", "codex"}:
            raise ModelGatewayError(f"不支持的模型提供方：{self.provider}")

        from app.analysis.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url=str(self.base_url),
            api_key=str(self.api_key),
            model_name=str(self.model_name),
            wire_api="responses" if self.provider == "codex" else self.wire_api,
            reasoning_effort=self.reasoning_effort,
            disable_response_storage=self.disable_response_storage,
            timeout=self.timeout_seconds,
        )
        return provider.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )


def parse_model_json(raw_content: str, schema: type[SchemaT]) -> SchemaT:
    try:
        payload = json.loads(_extract_json_text(raw_content))
    except json.JSONDecodeError as exc:
        raise ModelOutputValidationError("模型返回内容不是合法 JSON") from exc

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise ModelOutputValidationError(f"模型 JSON 未通过结构校验：{exc}") from exc


def _extract_json_text(raw_content: str) -> str:
    content = raw_content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return content
