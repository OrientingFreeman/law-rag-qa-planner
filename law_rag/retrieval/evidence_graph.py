from __future__ import annotations

from dataclasses import dataclass, asdict
import re

from law_rag.domain.models import SearchResult
from law_rag.ontology import DEFAULT_LEGAL_ONTOLOGY, LegalOntology
from law_rag.retrieval.ontology_filter import matched_issue_ids

ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")


@dataclass(slots=True)
class EvidenceNode:
    document_id: str
    citation: str
    law_id: str
    article_no: str
    document_type: str
    role: str
    issue_ids: list[str]
    score: float
    ontology_score: float
    issue_coverage: float


@dataclass(slots=True)
class EvidenceEdge:
    source_id: str
    relation: str
    target_id: str
    issue_ids: list[str]
    confidence: float
    reason: str


def _target_issue_ids(plan: object) -> list[str]:
    ontology = getattr(plan, "ontology", {}) or {}
    rows = ontology.get("concepts", []) if isinstance(ontology, dict) else []
    return [
        str(row["concept_id"])
        for row in rows
        if isinstance(row, dict) and row.get("category") == "legal_act" and row.get("concept_id")
    ]


def _article_tokens(text: str) -> set[str]:
    return {f"제{base}조" + (f"의{branch}" if branch else "") for base, branch in ARTICLE_RE.findall(text or "")}


def _paragraph_order(result: SearchResult) -> int:
    raw = str(result.provision.paragraph_no or "")
    circled = "①②③④⑤⑥⑦⑧⑨⑩"
    for index, token in enumerate(circled, start=1):
        if token in raw or token in result.provision.document_id:
            return index
    match = re.search(r"(?:제)?(\d+)항", raw)
    return int(match.group(1)) if match else 0


def _typed_relation(source: SearchResult, target: SearchResult, shared: set[str]) -> tuple[str, float, str] | None:
    if not shared:
        return None

    source_p = source.provision
    target_p = target.provision
    source_text = source_p.text or ""
    target_text = target_p.text or ""

    # A provision that explicitly names another article has the clearest directed relation.
    source_refs = _article_tokens(source_text)
    target_refs = _article_tokens(target_text)
    if target_p.article_no in source_refs:
        if any(token in source_text for token in ("위반", "중지", "과태료", "벌칙", "제재", "명할 수")):
            return "sanction_of", 0.98, f"{source_p.article_no}가 {target_p.article_no} 위반 또는 제재를 명시적으로 규정"
        return "references", 0.93, f"{source_p.article_no}가 {target_p.article_no}를 명시적으로 인용"
    if source_p.article_no in target_refs:
        if any(token in target_text for token in ("위반", "중지", "과태료", "벌칙", "제재", "명할 수")):
            return "subject_to_sanction", 0.98, f"{target_p.article_no}가 {source_p.article_no} 위반에 대한 효과를 규정"
        return "referenced_by", 0.93, f"{target_p.article_no}가 {source_p.article_no}를 명시적으로 인용"

    if source_p.law_id == target_p.law_id and source_p.article_no == target_p.article_no:
        # Structural relations run only from a later paragraph to an earlier rule.
        # This prevents a primary paragraph containing a general prohibition from
        # being mislabeled as prohibiting a later delegation/supplement paragraph.
        if _paragraph_order(source) <= _paragraph_order(target):
            return None
        source_is_prohibition = any(token in source_text for token in ("아니 된다", "금지", "초과하여서는", "초과하여"))
        source_is_exception = any(token in source_text for token in ("다만", "예외로", "적용하지 아니"))
        source_is_delegation = any(token in source_text for token in ("대통령령으로 정한다", "총리령으로 정한다", "부령으로 정한다"))
        if source_is_prohibition:
            return "prohibition_of", 0.96, "동일 조문의 후속 항이 기본 규칙에 대한 금지 또는 범위 제한을 규정"
        if source_is_exception:
            return "exception_of", 0.95, "동일 조문의 후속 항이 기본 규칙의 명시적 예외를 규정"
        if source_is_delegation:
            return "supplements", 0.94, "동일 조문의 후속 항이 세부 기준·절차를 하위 법령에 위임하여 기본 규칙을 보충"
        if source.evidence_role != "primary" and target.evidence_role == "primary":
            return "supplements", 0.88, "동일 조문의 후속 항이 기본 규칙의 세부사항을 보충"
        return None

    source_is_subordinate = source_p.document_type in {"시행령", "시행규칙"}
    target_is_subordinate = target_p.document_type in {"시행령", "시행규칙"}
    if source_is_subordinate and not target_is_subordinate:
        return "implements", 0.9, "하위 법령이 법률상 의무의 세부 기준을 규정"
    if target_is_subordinate and not source_is_subordinate:
        return "implemented_by", 0.9, "법률상 의무가 하위 법령에서 구체화됨"

    if target_is_subordinate and any(token in source_text for token in ("대통령령으로 정한다", "총리령으로 정한다", "부령으로 정한다")):
        return "delegates_to", 0.86, "상위 조문이 세부사항을 하위 법령에 위임"
    if source_is_subordinate and any(token in target_text for token in ("대통령령으로 정한다", "총리령으로 정한다", "부령으로 정한다")):
        return "delegated_by", 0.86, "연결 조문이 세부사항을 하위 법령에 위임"

    return "supports_same_issue", 0.72, "동일 법적 쟁점을 규율하는 보충 근거"


def _build_typed_edges(results: list[SearchResult], nodes: list[EvidenceNode]) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = []
    seen: set[tuple[str, str, str]] = set()
    # Compare all retained nodes. The old adjacent-only strategy missed explicit
    # statutory relationships whenever related articles were not consecutive.
    for source_index, source in enumerate(results):
        for target_index, target in enumerate(results):
            if source_index == target_index:
                continue
            shared = set(nodes[source_index].issue_ids).intersection(nodes[target_index].issue_ids)
            typed = _typed_relation(source, target, shared)
            if typed is None:
                continue
            relation, confidence, reason = typed
            marker = (source.provision.document_id, relation, target.provision.document_id)
            inverse_marker = (target.provision.document_id, relation, source.provision.document_id)
            if marker in seen or (relation == "supports_same_issue" and inverse_marker in seen):
                continue
            seen.add(marker)
            edges.append(EvidenceEdge(
                source_id=source.provision.document_id,
                relation=relation,
                target_id=target.provision.document_id,
                issue_ids=sorted(shared),
                confidence=round(confidence, 4),
                reason=reason,
            ))

    priority = {
        "sanction_of": 0,
        "subject_to_sanction": 0,
        "exception_of": 1,
        "prohibition_of": 1,
        "obligation_of": 1,
        "implements": 2,
        "implemented_by": 2,
        "delegates_to": 3,
        "delegated_by": 3,
        "references": 4,
        "referenced_by": 4,
        "supplements": 5,
        "supports_same_issue": 6,
    }
    edges.sort(key=lambda edge: (priority.get(edge.relation, 9), -edge.confidence, edge.source_id, edge.target_id))
    return edges



def _issue_label(issue_id: str) -> str:
    labels = {
        "cross_border_transfer": "개인정보 국외이전",
        "processing_delegation": "개인정보 처리위탁",
    }
    return labels.get(issue_id, issue_id)


def _build_issue_transitions(targets: list[str], nodes: list[EvidenceNode]) -> list[dict[str, object]]:
    transitions: list[dict[str, object]] = []
    present = set(targets)
    if {"processing_delegation", "cross_border_transfer"}.issubset(present):
        bridge = [node.citation for node in nodes if {"processing_delegation", "cross_border_transfer"}.issubset(set(node.issue_ids))]
        transitions.append({
            "source_issue_id": "processing_delegation",
            "relation": "triggers_additional_rule",
            "target_issue_id": "cross_border_transfer",
            "condition": "처리위탁 과정에서 개인정보가 국외로 이전되는 경우",
            "conclusion": "처리위탁 규율과 별도로 국외이전 요건을 추가 적용",
            "citations": bridge,
            "confidence": 0.97 if bridge else 0.82,
        })
        transitions.append({
            "source_issue_id": "cross_border_transfer",
            "relation": "co_applies_with",
            "target_issue_id": "processing_delegation",
            "condition": "국외이전의 방식이 처리위탁인 경우",
            "conclusion": "양 쟁점의 요건을 누적적으로 검토",
            "citations": bridge,
            "confidence": 0.97 if bridge else 0.82,
        })
    return transitions


def build_reasoning_path(plan: object, nodes: list[EvidenceNode], edges: list[EvidenceEdge]) -> dict[str, object]:
    targets = _target_issue_ids(plan)
    steps: list[dict[str, object]] = []
    transitions = _build_issue_transitions(targets, nodes)
    step_no = 1
    for issue in targets:
        issue_nodes = [node for node in nodes if issue in node.issue_ids]
        primary = [node for node in issue_nodes if node.role == "primary"]
        supporting = [node for node in issue_nodes if node.role in {"supporting", "implementing", "related"}]
        limitations = [node for node in issue_nodes if node.role == "exception"]
        cited = primary or issue_nodes[:1]
        steps.append({
            "step": step_no,
            "type": "identify_issue",
            "issue_id": issue,
            "question": f"{_issue_label(issue)} 쟁점이 질문 사실관계에 포함되는가?",
            "conclusion": "포함됨" if issue_nodes else "근거 부족",
            "citations": [node.citation for node in cited],
        })
        step_no += 1
        if cited:
            steps.append({
                "step": step_no,
                "type": "apply_primary_rule",
                "issue_id": issue,
                "question": "직접 적용되는 기본 규칙과 요건은 무엇인가?",
                "conclusion": "핵심 조문의 요건을 우선 적용",
                "citations": [node.citation for node in cited],
            })
            step_no += 1
        if limitations:
            steps.append({
                "step": step_no,
                "type": "check_exception_or_limitation",
                "issue_id": issue,
                "question": "예외·금지·범위 제한이 적용되는가?",
                "conclusion": "관련 제한 조문을 별도로 확인",
                "citations": [node.citation for node in limitations],
            })
            step_no += 1
        consequence_nodes = []
        consequence_ids = {
            edge.source_id for edge in edges if edge.relation in {"sanction_of", "subject_to_sanction"} and issue in edge.issue_ids
        }
        consequence_nodes = [node for node in issue_nodes if node.document_id in consequence_ids]
        if consequence_nodes:
            steps.append({
                "step": step_no,
                "type": "check_legal_consequence",
                "issue_id": issue,
                "question": "요건 위반 시 법적 효과나 제재는 무엇인가?",
                "conclusion": "위반 시 중지명령 등 별도 효과가 발생할 수 있음",
                "citations": [node.citation for node in consequence_nodes],
            })
            step_no += 1
        if supporting:
            steps.append({
                "step": step_no,
                "type": "confirm_supplementary_rules",
                "issue_id": issue,
                "question": "세부 절차 또는 보충 규정이 있는가?",
                "conclusion": "보충 조문과 하위 규정을 함께 확인",
                "citations": [node.citation for node in supporting],
            })
            step_no += 1

    covered = {issue for node in nodes for issue in node.issue_ids}
    return {
        "enabled": bool(targets),
        "complete": bool(targets) and all(issue in covered for issue in targets),
        "issue_order": targets,
        "steps": steps,
        "issue_transitions": transitions,
        "answer_contract": {
            "section_order": ["결론", "쟁점별 법적 판단", "적용 요건과 예외", "실무상 조치", "추가 확인 사실"],
            "must_follow_step_order": True,
            "allowed_citations": sorted({citation for step in steps for citation in step.get("citations", [])}),
            "must_explain_transitions": bool(transitions),
        },
        "final_instruction": "추론 단계와 쟁점 전이를 따라 결론→쟁점별 판단→요건·예외→실무조치 순서로 답변을 구성",
    }


def build_evidence_graph(
    plan: object,
    results: list[SearchResult],
    *,
    ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY,
) -> dict[str, object]:
    targets = _target_issue_ids(plan)
    target_set = set(targets)
    nodes: list[EvidenceNode] = []
    covered: set[str] = set()

    for index, result in enumerate(results):
        issues = sorted(matched_issue_ids(result, plan, ontology=ontology))
        covered.update(issues)
        coverage = len(issues) / len(target_set) if target_set else 1.0
        role = "primary" if issues and index < max(1, len(targets)) else "supporting"
        if result.retrieval_reason.startswith("related") or result.relation_score > 0:
            role = "implementing" if result.provision.document_type in {"시행령", "시행규칙"} else "related"
        if any(token in result.provision.text for token in ("다만", "제외", "아니 된다", "금지", "초과하여")) and issues:
            role = "exception" if role != "primary" else role

        result.evidence_role = role
        result.issue_ids = issues
        result.issue_coverage_score = coverage
        nodes.append(EvidenceNode(
            document_id=result.provision.document_id,
            citation=result.provision.citation_label(),
            law_id=result.provision.law_id,
            article_no=result.provision.article_no,
            document_type=result.provision.document_type,
            role=role,
            issue_ids=issues,
            score=round(result.score, 4),
            ontology_score=round(result.ontology_score, 4),
            issue_coverage=round(coverage, 4),
        ))

    edges = _build_typed_edges(results, nodes)
    missing = [issue for issue in targets if issue not in covered]
    reasoning_path = build_reasoning_path(plan, nodes, edges)
    return {
        "enabled": True,
        "issues": targets,
        "covered_issues": [issue for issue in targets if issue in covered],
        "missing_issues": missing,
        "coverage": round((len(covered) / len(targets)) if targets else 0.0, 4),
        "nodes": [asdict(node) for node in nodes],
        "edges": [asdict(edge) for edge in edges],
        "reasoning_path": reasoning_path,
    }
