from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


class GenerationError(RuntimeError):
    """Raised when a text-generation provider cannot produce a response."""


@dataclass(frozen=True)
class GenerationOutput:
    text: str
    provider: str
    model: str
    raw: dict[str, Any] | None = None
    request_id: str | None = None
    usage: dict[str, int] | None = None


class LlmProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, prompt: str) -> GenerationOutput:
        raise NotImplementedError

    def status(self) -> dict[str, object]:
        return {"provider": self.name, "configured": True}


class DisabledProvider(LlmProvider):
    name = "disabled"

    def generate(self, prompt: str) -> GenerationOutput:
        raise GenerationError(
            "LLM provider가 설정되지 않았습니다. LAW_RAG_LLM_PROVIDER를 설정하세요."
        )

    def status(self) -> dict[str, object]:
        return {"provider": self.name, "configured": False}


class DeterministicProvider(LlmProvider):
    """Offline provider used for local validation and automated tests."""

    name = "deterministic"

    def generate(self, prompt: str) -> GenerationOutput:
        evidence_lines = []
        for line in prompt.splitlines():
            stripped = line.strip()
            if stripped.startswith("법령명:") or stripped.startswith("조문:") or stripped.startswith("항:"):
                evidence_lines.append(stripped)
        citations = []
        for index in range(0, len(evidence_lines), 3):
            chunk = evidence_lines[index:index + 3]
            law = next((v.split(":", 1)[1].strip() for v in chunk if v.startswith("법령명:")), "")
            article = next((v.split(":", 1)[1].strip() for v in chunk if v.startswith("조문:")), "")
            paragraph = next((v.split(":", 1)[1].strip() for v in chunk if v.startswith("항:")), "")
            label = " ".join(part for part in (law, article, paragraph) if part)
            if label and label not in citations:
                citations.append(label)
        citation_text = ", ".join(citations[:5]) or "검색된 근거 없음"
        text = (
            "결론\n"
            "제공된 법령 근거를 기준으로 검토해야 합니다. 구체적인 적용은 사실관계에 따라 달라질 수 있습니다.\n\n"
            "실무상 조치\n"
            "- 질문의 적용 대상과 사실관계를 확인합니다.\n"
            "- 검색된 조문의 시행일과 예외 규정을 함께 검토합니다.\n\n"
            f"근거 조문\n{citation_text}\n\n"
            "추가 확인 사실\n처리 목적, 수집 항목, 보유 기간과 실제 동의 화면을 추가로 확인해야 합니다.\n\n"
            "답변 한계\n이 답변은 검색된 근거만을 사용한 로컬 검증용 결과이며 최종 법률판단이 아닙니다."
        )
        return GenerationOutput(text=text, provider=self.name, model="offline-template")


class _JsonHttpProvider(LlmProvider):
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise GenerationError("LLM API key가 비어 있습니다.")
        if not model.strip():
            raise GenerationError("LLM model이 비어 있습니다.")
        if timeout_seconds <= 0:
            raise GenerationError("LLM timeout은 0보다 커야 합니다.")
        if max_retries < 0 or max_retries > 10:
            raise GenerationError("LLM max retries는 0 이상 10 이하여야 합니다.")
        if not base_url.startswith(("http://", "https://")):
            raise GenerationError("LLM base URL은 http:// 또는 https://로 시작해야 합니다.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep

    def status(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "configured": True,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}{endpoint}",
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "law-rag-qa-planner/1.3",
                },
                method="POST",
            )
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                    parsed = json.loads(raw_body)
                    request_id = response.headers.get("x-request-id") if getattr(response, "headers", None) else None
                    if not isinstance(parsed, dict):
                        raise GenerationError("LLM 응답 JSON이 객체 형식이 아닙니다.")
                    return parsed, request_id
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = exc
                if exc.code not in self.retryable_statuses or attempt >= self.max_retries:
                    raise GenerationError(f"LLM HTTP 오류 {exc.code}: {detail[:500]}") from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise GenerationError(f"LLM 연결 또는 시간 초과 오류: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise GenerationError("LLM 응답이 유효한 JSON이 아닙니다.") from exc

            self._sleep(min(0.5 * (2**attempt), 4.0))

        raise GenerationError(f"LLM 호출 실패: {last_error}")


class OpenAIResponsesProvider(_JsonHttpProvider):
    """OpenAI Responses API provider."""

    name = "openai"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("base_url", "https://api.openai.com/v1")
        super().__init__(**kwargs)

    def generate(self, prompt: str) -> GenerationOutput:
        raw, header_request_id = self._post_json(
            "/responses",
            {
                "model": self.model,
                "input": prompt,
                "temperature": 0,
            },
        )
        text = _extract_responses_text(raw)
        if not text:
            raise GenerationError("OpenAI Responses API 응답에서 답변 본문을 찾을 수 없습니다.")
        usage = _normalize_usage(raw.get("usage"), input_key="input_tokens", output_key="output_tokens")
        return GenerationOutput(
            text=text,
            provider=self.name,
            model=str(raw.get("model") or self.model),
            raw=raw,
            request_id=str(raw.get("id") or header_request_id or "") or None,
            usage=usage,
        )


class OpenAICompatibleProvider(_JsonHttpProvider):
    """Generic OpenAI-compatible Chat Completions provider."""

    name = "openai_compatible"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("base_url", "https://api.openai.com/v1")
        super().__init__(**kwargs)

    def generate(self, prompt: str) -> GenerationOutput:
        raw, request_id = self._post_json(
            "/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
        )
        try:
            text = raw["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise GenerationError("Chat Completions 응답에서 답변 본문을 찾을 수 없습니다.") from exc
        if not text:
            raise GenerationError("LLM이 빈 답변을 반환했습니다.")
        usage = _normalize_usage(raw.get("usage"), input_key="prompt_tokens", output_key="completion_tokens")
        return GenerationOutput(
            text=text,
            provider=self.name,
            model=str(raw.get("model") or self.model),
            raw=raw,
            request_id=str(raw.get("id") or request_id or "") or None,
            usage=usage,
        )


def _extract_responses_text(raw: dict[str, Any]) -> str:
    direct = raw.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for output in raw.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                value = content.get("text")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(parts).strip()


def _normalize_usage(raw: Any, *, input_key: str, output_key: str) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = int(raw.get(input_key, 0) or 0)
    output_tokens = int(raw.get(output_key, 0) or 0)
    total_tokens = int(raw.get("total_tokens", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, str(default))
    try:
        return float(value)
    except ValueError as exc:
        raise GenerationError(f"{name}은 숫자여야 합니다: {value}") from exc


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except ValueError as exc:
        raise GenerationError(f"{name}은 정수여야 합니다: {value}") from exc


def provider_from_env() -> LlmProvider:
    provider = os.getenv("LAW_RAG_LLM_PROVIDER", "disabled").strip().lower()
    if provider in {"", "disabled", "none"}:
        return DisabledProvider()
    if provider in {"deterministic", "offline", "test"}:
        return DeterministicProvider()

    common = {
        "api_key": os.getenv("LAW_RAG_LLM_API_KEY", ""),
        "model": os.getenv("LAW_RAG_LLM_MODEL", "gpt-4.1-mini"),
        "base_url": os.getenv("LAW_RAG_LLM_BASE_URL", "https://api.openai.com/v1"),
        "timeout_seconds": _env_float("LAW_RAG_LLM_TIMEOUT", 30.0),
        "max_retries": _env_int("LAW_RAG_LLM_MAX_RETRIES", 2),
    }
    if provider == "openai":
        return OpenAIResponsesProvider(**common)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(**common)
    raise GenerationError(f"지원하지 않는 LLM provider입니다: {provider}")
