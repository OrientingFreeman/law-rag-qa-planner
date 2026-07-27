from __future__ import annotations

import os
from pathlib import Path

from law_rag.domain.models import SearchResult, format_provision_text
from law_rag.generation.composer import CompositionPlan, format_composition_plan

DEFAULT_PROMPT_VERSION = "answer_v22"


def _prompt_dir() -> Path:
    return Path(os.getenv("LAW_RAG_PROMPT_DIR", "prompts"))


def load_prompt_template(version: str | None = None) -> tuple[str, str]:
    selected = version or os.getenv("LAW_RAG_PROMPT_VERSION", DEFAULT_PROMPT_VERSION)
    directory = _prompt_dir()
    system_path = directory / "system.md"
    answer_path = directory / f"{selected}.md"
    if not system_path.exists() or not answer_path.exists():
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {system_path}, {answer_path}")
    return selected, answer_path.read_text(encoding="utf-8").strip().replace(
        "{system_prompt}", system_path.read_text(encoding="utf-8").strip()
    )


def build_grounded_prompt(query: str, results: list[SearchResult], *, version: str | None = None, reasoning_chain: list[dict[str, object]] | None = None, legal_intent: dict[str, object] | None = None, composition_plan: CompositionPlan | None = None, legal_reasoning_path: dict[str, object] | None = None) -> str:
    evidence = "\n\n".join(
        f"[근거 {result.rank}]\n{format_provision_text(result.provision)}"
        for result in results
    ) or "검색된 근거 없음"
    reasoning = "\n".join(
        f"{item.get('step')}. {item.get('citation')} - {item.get('reason')}"
        for item in (reasoning_chain or [])
    ) or "추론 경로 없음"
    path = legal_reasoning_path or {}
    step_text = "\n".join(
        f"{step.get('step')}. [{step.get('issue_id')}] {step.get('type')}: {step.get('question')} → {step.get('conclusion')} (허용 인용: {', '.join(step.get('citations', [])) or '없음'})"
        for step in path.get("steps", [])
    ) or "법적 추론 단계 없음"
    transition_text = "\n".join(
        f"- [{row.get('source_issue_id')}] --{row.get('relation')}--> [{row.get('target_issue_id')}]: {row.get('condition')} → {row.get('conclusion')} (근거: {', '.join(row.get('citations', [])) or '없음'})"
        for row in path.get("issue_transitions", [])
    ) or "- 없음"
    contract = path.get("answer_contract", {})
    path_text = "\n".join([
        "[추론 단계]", step_text,
        "[쟁점 전이]", transition_text,
        "[답변 계약]",
        f"- 섹션 순서: {' → '.join(contract.get('section_order', [])) or '미지정'}",
        f"- 단계 순서 준수: {contract.get('must_follow_step_order', False)}",
        f"- 전이 설명 필수: {contract.get('must_explain_transitions', False)}",
        f"- 전체 허용 인용: {', '.join(contract.get('allowed_citations', [])) or '없음'}",
    ])
    intent = legal_intent or {}
    intent_text = "\n".join([
        f"- 법률행위: {', '.join(intent.get('actions', [])) or '미분류'}",
        f"- 요청 유형: {', '.join(intent.get('requested_outputs', [])) or 'general'}",
        f"- 한정 요소: {', '.join(intent.get('qualifiers', [])) or '없음'}",
        f"- 복합 질문: {'예' if intent.get('is_compound') else '아니오'}",
    ])
    _, template = load_prompt_template(version)
    composer_text = format_composition_plan(composition_plan) if composition_plan else "구조화된 규칙 카드 없음"
    return template.replace("{query}", query).replace("{legal_intent}", intent_text).replace("{composition_plan}", composer_text).replace("{evidence}", evidence).replace("{reasoning_chain}", reasoning).replace("{legal_reasoning_path}", path_text).strip()
