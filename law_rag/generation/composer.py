from __future__ import annotations

from dataclasses import dataclass
import re

from law_rag.domain.models import SearchResult
from law_rag.generation.article_refs import extract_article_refs


@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    node_type: str
    title: str
    citation: str
    source_document_id: str
    source_text: str
    parent_id: str | None = None
    children: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "citation": self.citation,
            "source_document_id": self.source_document_id,
            "source_text": self.source_text,
            "parent_id": self.parent_id,
            "children": list(self.children),
        }


@dataclass(frozen=True)
class LegalRule:
    rule_id: str
    citation: str
    article_no: str
    role: str
    relation: str
    text: str
    source_document_id: str
    evidence_nodes: tuple[EvidenceNode, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "citation": self.citation,
            "article_no": self.article_no,
            "role": self.role,
            "relation": self.relation,
            "text": self.text,
            "source_document_id": self.source_document_id,
            "evidence_nodes": [node.to_dict() for node in self.evidence_nodes],
        }


@dataclass(frozen=True)
class CompositionPlan:
    rules: tuple[LegalRule, ...]
    allowed_citations: tuple[str, ...]
    required_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "rules": [rule.to_dict() for rule in self.rules],
            "allowed_citations": list(self.allowed_citations),
            "required_actions": list(self.required_actions),
        }


def _role_for(result: SearchResult, actions: set[str]) -> str:
    article = result.provision.article_no.replace(" ", "")
    if "처리위탁" in actions and article == "제26조":
        return "primary"
    if "국외이전" in actions and article == "제28조의8":
        return "primary"
    if result.retrieval_reason in {"direct", "planned"}:
        return "primary"
    return "supporting"


def _build_evidence_nodes(result: SearchResult, rule_id: str) -> tuple[EvidenceNode, ...]:
    provision = result.provision
    children: list[EvidenceNode] = []
    for index, item in enumerate(result.sub_provisions, start=1):
        source_text = str(item.get("text", "")).strip()
        if not source_text:
            continue
        children.append(EvidenceNode(
            node_id=f"{rule_id}:evidence:{index}",
            node_type="sub_provision",
            title=_compact_sub_requirement(source_text),
            citation=str(item.get("citation") or provision.citation_label()),
            source_document_id=str(item.get("document_id") or provision.document_id),
            source_text=source_text,
            parent_id=f"{rule_id}:evidence:root",
        ))

    if not children:
        _, parsed_items = _evidence_excerpt(provision.text)
        for index, source_text in enumerate(parsed_items, start=1):
            children.append(EvidenceNode(
                node_id=f"{rule_id}:evidence:{index}",
                node_type="sub_provision",
                title=_compact_sub_requirement(source_text),
                citation=provision.citation_label(),
                source_document_id=provision.document_id,
                source_text=source_text,
                parent_id=f"{rule_id}:evidence:root",
            ))

    root = EvidenceNode(
        node_id=f"{rule_id}:evidence:root",
        node_type="rule",
        title=_compact_requirement(provision.text.splitlines()[0], article_no=provision.article_no),
        citation=provision.citation_label(),
        source_document_id=provision.document_id,
        source_text=provision.text.strip(),
        children=tuple(node.node_id for node in children),
    )
    return (root, *children)


def build_composition_plan(
    results: list[SearchResult],
    legal_intent: dict[str, object] | None = None,
    *,
    max_rules: int = 6,
) -> CompositionPlan:
    intent = legal_intent or {}
    actions = {str(item) for item in intent.get("actions", [])}
    selected: list[LegalRule] = []
    seen: set[tuple[str, str | None]] = set()

    # Preserve retrieval order but prevent one article from consuming every rule slot.
    for result in results:
        provision = result.provision
        key = (provision.article_no, provision.paragraph_no)
        if key in seen:
            continue
        seen.add(key)
        rule_id = f"R{len(selected) + 1}"
        selected.append(
            LegalRule(
                rule_id=rule_id,
                citation=provision.citation_label(),
                article_no=provision.article_no.replace(" ", ""),
                role=_role_for(result, actions),
                relation=result.retrieval_reason,
                text=provision.text.strip(),
                source_document_id=provision.document_id,
                evidence_nodes=_build_evidence_nodes(result, rule_id),
            )
        )
        if len(selected) >= max_rules:
            break

    selected.sort(key=lambda rule: (0 if rule.role == "primary" else 1, int(rule.rule_id[1:])))
    # Reassign stable rule IDs after priority sorting.
    normalized = tuple(
        LegalRule(
            rule_id=f"R{index}",
            citation=rule.citation,
            article_no=rule.article_no,
            role=rule.role,
            relation=rule.relation,
            text=rule.text,
            source_document_id=rule.source_document_id,
            evidence_nodes=tuple(
                EvidenceNode(
                    node_id=node.node_id.replace(rule.rule_id, f"R{index}", 1),
                    node_type=node.node_type,
                    title=node.title,
                    citation=node.citation,
                    source_document_id=node.source_document_id,
                    source_text=node.source_text,
                    parent_id=node.parent_id.replace(rule.rule_id, f"R{index}", 1) if node.parent_id else None,
                    children=tuple(child.replace(rule.rule_id, f"R{index}", 1) for child in node.children),
                )
                for node in rule.evidence_nodes
            ),
        )
        for index, rule in enumerate(selected, start=1)
    )
    return CompositionPlan(
        rules=normalized,
        allowed_citations=tuple(rule.citation for rule in normalized),
        required_actions=tuple(str(item) for item in intent.get("actions", [])),
    )


def format_composition_plan(plan: CompositionPlan) -> str:
    allowed = "\n".join(f"- {citation}" for citation in plan.allowed_citations) or "- 없음"
    rules = "\n\n".join(
        "\n".join(
            [
                f"[{rule.rule_id}]",
                f"역할: {rule.role}",
                f"관계: {rule.relation}",
                f"허용 인용: {rule.citation}",
                f"근거 원문: {rule.text}",
            ]
        )
        for rule in plan.rules
    ) or "규칙 카드 없음"
    return f"[허용 인용 목록]\n{allowed}\n\n[구조화된 규칙 카드]\n{rules}"


def repair_ambiguous_article_citations(answer: str, results: list[SearchResult]) -> tuple[str, list[dict[str, str]]]:
    """Repair a shortened article citation only when the retrieved target is unique.

    Example: 제28조 -> 제28조의8 is safe only when 제28조 itself was not retrieved and
    exactly one retrieved article starts with 제28조의.
    """
    retrieved = {result.provision.article_no.replace(" ", "") for result in results}
    repairs: list[dict[str, str]] = []
    rewritten = answer
    cited = set(extract_article_refs(answer))
    for article in sorted(cited):
        if article in retrieved or "의" in article:
            continue
        stem = article[:-1] if article.endswith("조") else article
        candidates = sorted(item for item in retrieved if item.startswith(stem + "조의"))
        if len(candidates) != 1:
            continue
        replacement = candidates[0]
        pattern = re.compile(re.escape(article) + r"(?!의\d+)")
        updated = pattern.sub(replacement, rewritten)
        if updated != rewritten:
            repairs.append({"from": article, "to": replacement})
            rewritten = updated
    return rewritten, repairs


def _clean_evidence_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    cleaned = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", cleaned)
    return cleaned.strip()


def _evidence_excerpt(text: str, *, max_items: int = 5) -> tuple[str, list[str]]:
    """Return exact evidence excerpts without creating new legal claims."""
    cleaned = _clean_evidence_text(text)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "", []

    lead = lines[0]
    items: list[str] = []
    for line in lines[1:]:
        match = re.match(r"^(\d+(?:의\d+)?)\.\s*(.+)$", line)
        if not match:
            continue
        item = match.group(2).strip()
        if item and item not in items:
            items.append(item)
        if len(items) >= max_items:
            break
    return lead, items




def _compact_requirement(text: str, *, article_no: str = "") -> str:
    """Convert an exact statutory sentence into a short, source-bound checklist label."""
    cleaned = _clean_evidence_text(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if article_no.replace(" ", "") == "제28조의8" and "국외" in cleaned and "이전할 수 있다" in cleaned:
        return "적법한 국외이전 근거를 선택·확인"

    patterns: list[tuple[str, str]] = [
        (r".*처리 (?:업무를 )?위탁.*문서로 하여야 한다.*", "위탁계약을 문서로 작성"),
        (r".*위탁받은 해당 업무 범위를 초과하여.*이용하거나.*제3자에게 제공하여서는 아니 된다.*", "위탁받은 업무 범위를 초과한 이용·제공 금지"),
        (r".*이 법을 위반하는 사항을 내용으로 하는.*국외 이전.*계약을 체결하여서는 아니 된다.*", "법 위반 내용을 포함한 국외이전 계약 금지"),
        (r".*개인정보를 국외로.*(?:제공|처리위탁|보관).*이전.*하여서는 아니 된다.*다만.*이전할 수 있다.*", "적법한 국외이전 근거를 선택·확인"),
    ]
    for pattern, label in patterns:
        if re.match(pattern, cleaned):
            return label

    # Generic de-legalization: preserve the operative phrase while removing boilerplate.
    generic = re.sub(r"^개인정보처리자는\s*", "", cleaned)
    generic = re.sub(r"^수탁자는\s*", "", generic)
    generic = re.sub(r"^.*?경우에는\s*", "", generic, count=1)
    generic = re.sub(r"(?:하여야|해야) 한다\.?$", "", generic)
    generic = re.sub(r"하여서는 아니 된다\.?$", " 금지", generic)
    generic = re.sub(r"할 수 있다\.?$", " 가능", generic)
    generic = generic.strip(" .")
    if len(generic) > 72:
        generic = generic[:69].rstrip() + "…"
    return generic or f"{article_no} 요건 확인"


def _compact_sub_requirement(text: str) -> str:
    """Convert statutory sub-items into concise, operational checklist actions.

    The mapping stays deterministic and source-bound: it only rewrites phrases that
    are explicitly present in the retrieved provision and retains the original text
    separately in ``source_checklist`` / ``checklist_evidence``.
    """
    cleaned = re.sub(r"^\s*(?:\d+(?:의\d+)?\.|[가-힣]\.)\s*", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    patterns: list[tuple[str, str]] = [
        (r".*국외 이전에 관한 별도의 동의.*", "국외이전 별도 동의 확보"),
        (r".*법률.*조약.*국제협정.*특별한 규정.*", "법률·조약·국제협정상 이전 근거 확인"),
        (r".*계약의 체결 및 이행.*처리위탁.*보관.*", "계약 이행 목적의 위탁·보관 요건 확인"),
        (r".*개인정보 처리방침에 공개.*", "국외이전 사항을 처리방침에 공개"),
        (r".*정보주체에게 알린.*", "국외이전 사항을 정보주체에게 고지"),
        (r".*개인정보 보호 인증.*조치를 모두.*", "인증받은 이전받는 자와 필수 보호조치 확인"),
        (r".*개인정보 보호에 필요한 안전조치.*권리보장.*", "안전조치와 정보주체 권리보장 조치 확인"),
        (r".*인증받은 사항.*이행.*", "이전 국가에서 인증사항 이행 조치 확인"),
        (r".*보호체계.*실질적으로 동등한 수준.*보호위원회가 인정.*", "동등 보호수준 인정 국가·국제기구 여부 확인"),
        (r".*위탁업무 수행 목적 외.*처리 금지.*", "위탁 목적 외 개인정보 처리 금지"),
        (r".*기술적.*관리적 보호조치.*", "기술적·관리적 보호조치 반영"),
        (r".*안전한 관리.*대통령령.*", "대통령령상 안전관리 사항 반영"),
        (r".*위탁하는 사무의 목적 및 범위.*", "위탁 목적과 업무 범위 명시"),
        (r".*재위탁 제한.*", "재위탁 제한 조건 명시"),
        (r".*손해배상.*책임.*", "의무 위반 시 책임과 손해배상 기준 명시"),
    ]
    for pattern, label in patterns:
        if re.match(pattern, cleaned):
            return label

    cleaned = re.sub(r"에 관한 사항$", "", cleaned)
    cleaned = re.sub(r"(?:한|인)? 경우$", "", cleaned)
    cleaned = cleaned.strip(" .")
    if len(cleaned) > 54:
        cleaned = cleaned[:51].rstrip() + "…"
    return cleaned

def _action_for_rule(rule: LegalRule, required_actions: tuple[str, ...]) -> str:
    article = rule.article_no.replace(" ", "")
    if article == "제26조":
        return "처리위탁"
    if article == "제28조의8":
        return "국외이전"
    if "국외" in rule.text:
        return "국외이전"
    if "처리위탁" in rule.text:
        return "처리위탁"
    if len(required_actions) == 1:
        return required_actions[0]
    return "공통"


def _action_label(action: str) -> str:
    return {
        "처리위탁": "처리위탁 계약과 수탁자 관리",
        "국외이전": "국외 이전 근거와 고지·동의",
        "공통": "공통 확인사항",
    }.get(action, action)


def build_presentation_outline(plan: CompositionPlan) -> dict[str, object]:
    """Create a user-facing outline while preserving evidence provenance."""
    primary = [rule for rule in plan.rules if rule.role == "primary"] or list(plan.rules[:2])
    groups: dict[str, list[dict[str, object]]] = {}
    for rule in primary:
        action = _action_for_rule(rule, plan.required_actions)
        lead, items = _evidence_excerpt(rule.text)
        compact_items = [_compact_sub_requirement(item) for item in items]
        groups.setdefault(action, []).append({
            "trace_id": f"{rule.rule_id}:lead",
            "rule_id": rule.rule_id,
            "citation": rule.citation,
            "article_no": rule.article_no,
            "display_text": _compact_requirement(lead, article_no=rule.article_no),
            "source_text": lead,
            "checklist": compact_items,
            "source_checklist": items,
            "checklist_evidence": [
                {
                    "trace_id": f"{rule.rule_id}:item:{index}",
                    "display_text": display_text,
                    "source_text": source_text,
                    "citation": rule.citation,
                    "source_document_id": rule.source_document_id,
                }
                for index, (display_text, source_text) in enumerate(
                    zip(compact_items, items), start=1
                )
            ],
            "source_document_id": rule.source_document_id,
            "supporting_node_ids": [node.node_id for node in rule.evidence_nodes],
            "supporting_citations": [
                {
                    "citation": node.citation,
                    "role": "parent" if node.node_type == "rule" else "primary",
                    "node_id": node.node_id,
                    "source_document_id": node.source_document_id,
                }
                for node in rule.evidence_nodes
            ],
        })
    ordered_actions = [action for action in plan.required_actions if action in groups]
    ordered_actions.extend(action for action in groups if action not in ordered_actions)
    all_nodes = [node for rule in primary for node in rule.evidence_nodes]
    return {
        "mode": "action_checklist",
        "provenance_graph": {
            "nodes": [node.to_dict() for node in all_nodes],
            "root_node_ids": [node.node_id for node in all_nodes if node.parent_id is None],
            "node_count": len(all_nodes),
            "edge_count": sum(len(node.children) for node in all_nodes),
            "fully_connected": all(
                child in {candidate.node_id for candidate in all_nodes}
                for node in all_nodes for child in node.children
            ),
        },
        "actions": [
            {
                "action": action,
                "label": _action_label(action),
                "rules": groups[action],
            }
            for action in ordered_actions
        ],
    }


def compose_evidence_fallback(question: str, plan: CompositionPlan) -> str:
    outline = build_presentation_outline(plan)
    action_rows = list(outline["actions"])
    supporting = [
        rule for rule in plan.rules
        if rule.role != "primary" and rule.relation in {"direct", "planned"}
    ]

    lines = [
        "결론",
        "검색된 법령 근거상 질문에 포함된 법률행위별 요건을 각각 확인해야 합니다.",
        "",
        "판단 순서",
    ]
    for index, row in enumerate(action_rows, start=1):
        lines.append(f"{index}. {row['label']}")

    lines.extend(["", "실무 체크리스트"])
    for row in action_rows:
        lines.append(f"[{row['label']}]")
        for rule in row["rules"]:
            citation = str(rule["citation"])
            display_text = str(rule["display_text"])
            items = list(rule["checklist"])
            if display_text:
                lines.append(f"- □ {display_text} ({citation})")
            for item in items:
                lines.append(f"  - □ {item} ({citation})")

    lines.extend(["", "근거 조문"])
    seen_citations: set[str] = set()
    for row in action_rows:
        for rule in row["rules"]:
            citation = str(rule["citation"])
            if citation in seen_citations:
                continue
            seen_citations.add(citation)
            lines.append(f"- {citation}")

    if supporting:
        lines.extend(["", "보충 확인"])
        for rule in supporting:
            lead, _ = _evidence_excerpt(rule.text, max_items=0)
            lines.append(f"- {lead} ({rule.citation})" if lead else f"- {rule.citation}")

    lines.extend(
        [
            "",
            "추가 확인 사실",
            "구체적인 계약 구조, 이전 국가, 수탁자 지위 및 실제 고지·동의 방식은 추가 사실 확인이 필요합니다.",
        ]
    )
    return "\n".join(lines).strip()
