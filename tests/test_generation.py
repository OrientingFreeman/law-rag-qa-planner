from fastapi.testclient import TestClient

from law_rag.api.app import create_app
from law_rag.generation.citations import validate_citations
from law_rag.generation.providers import DeterministicProvider, DisabledProvider
from law_rag.service import LawRagService


def test_deterministic_provider_generates_cited_answer():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert response["generation_status"] == "completed"
    assert response["citation_validation"]["valid"] is True
    assert "개인정보 보호법 제15조" in response["answer"]


def test_disabled_provider_returns_safe_failure():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DisabledProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert response["generation_status"] == "failed"
    assert response["generation_error"]
    assert response["results"]


def test_answer_endpoint_with_offline_provider(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "deterministic")
    app = create_app(data_path="tests/fixtures/legal_corpus.json", domains_path="domains")
    with TestClient(app) as api:
        response = api.post(
            "/answer",
            json={
                "question": "개인정보 수집 동의 요건은?",
                "domain": "digital_business",
                "top_k": 1,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deterministic"
    assert body["citation_validation"]["valid"] is True


def test_citation_validator_rejects_unretrieved_article():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    domain = service.registry.get("digital_business")
    results = service.retriever.retrieve(
        "개인정보 수집 동의 요건은?",
        domain=domain,
        top_k=1,
    )
    validation = validate_citations("개인정보 보호법 제999조에 따른다.", results)
    assert validation["valid"] is False
    assert "제999조" in validation["unsupported_articles"]

import io
import json
import urllib.error

import pytest

from law_rag.generation.providers import (
    GenerationError,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    provider_from_env,
)


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_openai_responses_provider_parses_text_usage_and_request_id():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "id": "resp_123",
                "model": "gpt-test",
                "output": [
                    {"content": [{"type": "output_text", "text": "개인정보 보호법 제15조에 따릅니다."}]}
                ],
                "usage": {"input_tokens": 10, "output_tokens": 7, "total_tokens": 17},
            }
        )

    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="gpt-test",
        opener=opener,
        sleep=lambda _: None,
    )
    output = provider.generate("grounded prompt")

    assert captured["url"].endswith("/responses")
    assert captured["payload"]["input"] == "grounded prompt"
    assert output.text == "개인정보 보호법 제15조에 따릅니다."
    assert output.request_id == "resp_123"
    assert output.usage == {"input_tokens": 10, "output_tokens": 7, "total_tokens": 17}


def test_openai_compatible_provider_uses_chat_completions():
    def opener(request, timeout):
        assert request.full_url.endswith("/chat/completions")
        return FakeResponse(
            {
                "id": "chatcmpl_123",
                "model": "local-model",
                "choices": [{"message": {"content": "개인정보 보호법 제15조입니다."}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
            }
        )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="local-model",
        base_url="http://localhost:1234/v1",
        opener=opener,
        sleep=lambda _: None,
    )
    output = provider.generate("prompt")
    assert output.provider == "openai_compatible"
    assert output.usage["total_tokens"] == 13


def test_provider_retries_retryable_http_error():
    attempts = {"count": 0}

    def opener(request, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                hdrs={},
                fp=io.BytesIO(b'{"error":"rate limited"}'),
            )
        return FakeResponse({"output_text": "개인정보 보호법 제15조", "model": "gpt-test"})

    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="gpt-test",
        max_retries=1,
        opener=opener,
        sleep=lambda _: None,
    )
    assert provider.generate("prompt").text == "개인정보 보호법 제15조"
    assert attempts["count"] == 2


def test_provider_from_env_rejects_invalid_timeout(monkeypatch):
    monkeypatch.setenv("LAW_RAG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LAW_RAG_LLM_API_KEY", "test-key")
    monkeypatch.setenv("LAW_RAG_LLM_TIMEOUT", "not-a-number")
    with pytest.raises(GenerationError, match="LAW_RAG_LLM_TIMEOUT"):
        provider_from_env()


def test_service_propagates_provider_usage_and_request_id():
    class StubProvider(DeterministicProvider):
        name = "stub-openai"

        def generate(self, prompt):
            from law_rag.generation.providers import GenerationOutput
            return GenerationOutput(
                text="개인정보 보호법 제15조에 따른 수집 근거를 확인해야 합니다.",
                provider=self.name,
                model="stub-model",
                request_id="resp_test_123",
                usage={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            )

    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=StubProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert response["generation_request_id"] == "resp_test_123"
    assert response["generation_usage"]["total_tokens"] == 30


def test_answer_v3_returns_structured_legal_qa_fields():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=3,
    )
    assert response["prompt_version"] == "answer_v22"
    assert response["answer_structure"]["conclusion"]
    assert response["answer_structure"]["legal_basis"][0]["role"] == "primary"
    assert response["retrieval_explanation"]["selected"] is True
    assert response["retrieval_explanation"]["reasons"]
    assert isinstance(response["related_provisions"], list)


def test_answer_excludes_unrelated_candidate_and_phantom_conflict():
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )

    response = service.answer(
        "개인정보 수집 동의 요건은 무엇인가요?",
        domain_id="digital_business",
        top_k=3,
    )

    citations = [row["citation"] for row in response["results"]]
    reasoning_citations = [row["citation"] for row in response["reasoning_chain"]]
    reasoning_steps = [
        row["type"] for row in response["legal_reasoning_path"]["steps"]
    ]

    assert response["abstain"] is False
    assert response["multi_path_reasoning"]["status"] == "not_applicable"
    assert all("제15조의3" not in citation for citation in citations)
    assert all("제15조의3" not in citation for citation in reasoning_citations)
    assert "resolve_rule_conflict" not in reasoning_steps
    assert "제15조의3" not in response["display_answer"]
    assert "규칙 충돌" not in response["display_answer"]


def test_answer_v3_extracts_list_points_and_contextual_facts():
    from law_rag.generation.analysis import build_answer_structure, classify_question
    from law_rag.retrieval.aggregation import aggregate_evidence

    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    question = "개인정보 처리방침에는 어떤 내용을 포함해야 하나?"
    domain = service.registry.get("digital_business")
    raw = service.retriever.retrieve(question, domain=domain, top_k=15)
    results = aggregate_evidence(raw, service.provisions, limit=5)
    structure = build_answer_structure(question, results)

    assert classify_question(question) == "list"
    assert structure["answer_type"] == "list"
    assert any("개인정보의 처리 목적" in point for point in structure["key_points"])
    assert "실제 제3자 제공 여부" in structure["facts_to_confirm"]
    assert "다음" in structure["conclusion"]


def test_answer_includes_grounding_validation_and_confidence_components():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert "grounding_validation" in response
    assert 0.0 <= response["grounding_validation"]["coverage"] <= 1.0
    assert set(response["confidence"]["components"]) == {"retrieval", "coverage", "citation", "grounding"}


def test_grounding_validator_flags_unsupported_legal_claim():
    from law_rag.generation.grounding import validate_grounding
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    domain = service.registry.get("digital_business")
    results = service.retriever.retrieve("개인정보 수집 동의 요건은?", domain=domain, top_k=1)
    validation = validate_grounding("사업자는 모든 정보를 100년간 보관해야 합니다.", results)
    assert validation["valid"] is False
    assert validation["unsupported_claims"]


def test_answer_v16_returns_reasoning_chain_and_graph_expansion():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=3,
    )
    assert response["prompt_version"] == "answer_v22"
    assert response["reasoning_chain"]
    assert response["reasoning_chain"][0]["relation"] == "direct"
    assert response["graph_expansion"]["enabled"] is True
    assert response["graph_expansion"]["expanded_count"] >= 0


def test_composer_repairs_unique_shortened_article_citation():
    from law_rag.generation.composer import repair_ambiguous_article_citations
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    domain = service.registry.get("digital_business")
    results = service.retriever.retrieve(
        "개인정보 국외 이전 요건은?", domain=domain, top_k=10
    )
    target = [r for r in results if r.provision.article_no == "제28조의8"]
    repaired, repairs = repair_ambiguous_article_citations(
        "개인정보 보호법 제28조에 따릅니다.", target
    )
    assert "제28조의8" in repaired
    assert repairs == [{"from": "제28조", "to": "제28조의8"}]


def test_structured_composer_falls_back_when_llm_is_ungrounded():
    from law_rag.generation.providers import GenerationOutput

    class HallucinatingProvider(DeterministicProvider):
        name = "hallucinating"

        def generate(self, prompt):
            return GenerationOutput(
                text="모든 개인정보는 100년간 보관해야 합니다. 개인정보 보호법 제999조에 따릅니다.",
                provider=self.name,
                model="bad-model",
            )

    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=HallucinatingProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert response["generation_status"] == "completed"
    assert response["composition"]["fallback_used"] is True
    assert response["citation_validation"]["valid"] is True
    assert response["grounding_validation"]["coverage"] >= 0.8
    assert "제999조" not in response["answer"]


def test_answer_v16_exposes_composition_plan():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    assert response["prompt_version"] == "answer_v22"
    assert response["composition"]["plan"]["rules"]
    assert response["composition"]["plan"]["allowed_citations"]


def test_citation_parser_preserves_branch_article_number():
    from law_rag.generation.article_refs import extract_article_refs

    assert extract_article_refs("개인정보 보호법 제28조의8 제1항") == ["제28조의8"]


def test_citation_validator_does_not_truncate_branch_article():
    from law_rag.generation.citations import validate_citations

    from law_rag.domain.models import LegalProvision, SearchResult

    target = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1",
            law_id="011357",
            law_name="개인정보 보호법",
            article_no="제28조의8",
            paragraph_no="제1항",
            text="개인정보의 국외 이전에 관한 규정",
        ),
        score=1.0,
    )]
    validation = validate_citations("개인정보 보호법 제28조의8에 따릅니다.", target)
    assert validation["valid"] is True
    assert validation["cited_articles"] == ["제28조의8"]


def test_evidence_fallback_omits_unrelated_graph_dump():
    from law_rag.generation.composer import build_composition_plan, compose_evidence_fallback

    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    results = service.retriever.retrieve(
        "개인정보 수집 동의 요건은?", domain=service.registry.get("digital_business"), top_k=3
    )
    plan = build_composition_plan(results, {"actions": []})
    answer = compose_evidence_fallback("개인정보 수집 동의 요건은?", plan)
    assert "실무 체크리스트" in answer
    assert "검색된 법령 근거상 질문에 포함된 법률행위별 요건을 각각 확인해야 합니다." in answer
    assert "질문:" not in answer


def test_citation_scope_accepts_article_referenced_inside_official_evidence():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.citations import validate_citations

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1",
            law_id="011357",
            law_name="개인정보 보호법",
            article_no="제28조의8",
            paragraph_no="제1항",
            text="개인정보를 이전받는 자가 제32조의2에 따른 인증을 받은 경우",
        ),
        score=1.0,
        retrieval_reason="planned",
    )]
    validation = validate_citations(
        "개인정보 보호법 제28조의8 및 제32조의2를 확인합니다.", results
    )
    assert validation["valid"] is True
    assert validation["citation_scopes"]["제28조의8"] == "direct"
    assert validation["citation_scopes"]["제32조의2"] == "referenced"
    assert "제32조의2" in validation["scope"]["referenced_articles"]


def test_citation_scope_still_rejects_unseen_article():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.citations import validate_citations

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1",
            law_id="011357",
            law_name="개인정보 보호법",
            article_no="제28조의8",
            text="제32조의2에 따른 인증을 받은 경우",
        ),
        score=1.0,
    )]
    validation = validate_citations("개인정보 보호법 제999조에 따릅니다.", results)
    assert validation["valid"] is False
    assert validation["citation_scopes"]["제999조"] == "unsupported"


def test_evidence_fallback_reference_is_not_citation_invalid():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.answer import generate_grounded_answer
    from law_rag.generation.providers import GenerationOutput

    class LowGroundingProvider(DeterministicProvider):
        def generate(self, prompt):
            return GenerationOutput(
                text="개인정보 보호법 제28조의8에 따릅니다. 추가 검토가 필요합니다.",
                provider="test",
                model="test",
            )

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1",
            law_id="011357",
            law_name="개인정보 보호법",
            article_no="제28조의8",
            paragraph_no="제1항",
            text="개인정보를 이전받는 자가 제32조의2에 따른 인증을 받은 경우\n1. 필요한 조치를 모두 한 경우",
        ),
        score=1.0,
        retrieval_reason="planned",
    )]
    response = generate_grounded_answer(
        "국외 이전 요건은?", results, LowGroundingProvider(),
        legal_intent={"actions": ["국외이전"]},
    )
    assert response.citation_validation["valid"] is True
    assert response.generation_status == "completed"


def test_action_checklist_presentation_groups_compound_question():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline, compose_evidence_fallback

    results = [
        SearchResult(
            provision=LegalProvision(
                document_id="pipa:28-8:1", law_id="011357", law_name="개인정보 보호법",
                article_no="제28조의8", paragraph_no="제1항",
                text="개인정보를 국외로 이전하여서는 아니 된다. 다만 다음 각 호의 어느 하나에 해당하면 이전할 수 있다.\n1. 별도의 동의를 받은 경우\n2. 계약 이행을 위하여 처리위탁이 필요한 경우",
            ), score=1.0, retrieval_reason="planned",
        ),
        SearchResult(
            provision=LegalProvision(
                document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
                article_no="제26조", paragraph_no="제1항",
                text="처리 업무를 위탁하는 경우에는 문서로 하여야 한다.\n1. 목적 외 처리 금지\n2. 보호조치",
            ), score=0.9, retrieval_reason="planned",
        ),
    ]
    plan = build_composition_plan(results, {"actions": ["처리위탁", "국외이전"]})
    outline = build_presentation_outline(plan)
    answer = compose_evidence_fallback("위탁하면서 국외 이전하는 절차는?", plan)

    assert outline["mode"] == "action_checklist"
    assert [row["action"] for row in outline["actions"]] == ["처리위탁", "국외이전"]
    assert "판단 순서" in answer
    assert "실무 체크리스트" in answer
    assert "[처리위탁 계약과 수탁자 관리]" in answer
    assert "[국외 이전 근거와 고지·동의]" in answer
    assert answer.count("개인정보 보호법 제28조의8 제1항") == 4


def test_action_checklist_fallback_remains_grounded_and_citation_valid():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.answer import generate_grounded_answer
    from law_rag.generation.providers import DeterministicProvider, GenerationOutput

    class BadProvider(DeterministicProvider):
        def generate(self, prompt):
            return GenerationOutput(text="제999조에 따라 100년 보관합니다.", provider="test", model="test")

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="처리 업무를 위탁하는 경우에는 문서로 하여야 한다.\n1. 목적 외 처리 금지\n2. 보호조치",
        ), score=1.0, retrieval_reason="planned",
    )]
    response = generate_grounded_answer(
        "처리위탁 절차는?", results, BadProvider(), legal_intent={"actions": ["처리위탁"]}
    )
    assert response.generation_status == "completed"
    assert response.citation_validation["valid"] is True
    assert response.grounding_validation["coverage"] >= 0.8
    assert response.composition["presentation"]["mode"] == "action_checklist"


def test_compact_checklist_uses_action_labels_and_preserves_sources():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline, compose_evidence_fallback

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보처리자가 제3자에게 개인정보의 처리 업무를 위탁하는 경우에는 다음 각 호의 내용이 포함된 문서로 하여야 한다.\n1. 위탁업무 수행 목적 외 개인정보의 처리 금지에 관한 사항\n2. 개인정보의 기술적·관리적 보호조치에 관한 사항",
        ), score=1.0, retrieval_reason="planned",
    )]
    plan = build_composition_plan(results, {"actions": ["처리위탁"]})
    outline = build_presentation_outline(plan)
    rule = outline["actions"][0]["rules"][0]
    answer = compose_evidence_fallback("처리위탁 절차는?", plan)

    assert rule["display_text"] == "위탁계약을 문서로 작성"
    assert "개인정보처리자가 제3자에게" in rule["source_text"]
    assert rule["checklist"] == ["위탁 목적 외 개인정보 처리 금지", "기술적·관리적 보호조치 반영"]
    assert "□ 위탁계약을 문서로 작성" in answer
    assert "개인정보처리자가 제3자에게 개인정보의 처리 업무를 위탁하는 경우에는" not in answer


def test_compact_checklist_fallback_is_grounded_and_citation_valid():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.answer import generate_grounded_answer
    from law_rag.generation.providers import DeterministicProvider, GenerationOutput

    class BadProvider(DeterministicProvider):
        def generate(self, prompt):
            return GenerationOutput(text="제999조에 따라 영구 보관합니다.", provider="test", model="test")

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:5", law_id="011357", law_name="개인정보 보호법",
            article_no="제28조의8", paragraph_no="제5항",
            text="개인정보처리자는 이 법을 위반하는 사항을 내용으로 하는 개인정보의 국외 이전에 관한 계약을 체결하여서는 아니 된다.",
        ), score=1.0, retrieval_reason="planned",
    )]
    response = generate_grounded_answer("국외 이전 계약 요건은?", results, BadProvider(), legal_intent={"actions": ["국외이전"]})
    assert response.generation_status == "completed"
    assert response.citation_validation["valid"] is True
    assert response.grounding_validation["coverage"] >= 0.8
    assert "법 위반 내용을 포함한 국외이전 계약 금지" in response.answer


def test_grounding_claims_expose_complete_audit_trail():
    from law_rag.generation.grounding import validate_grounding

    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    domain = service.registry.get("digital_business")
    _, raw_results = service._planned_raw_results(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain=domain,
        requested_top_k=5,
        as_of_date=None,
    )
    results = raw_results
    answer = "□ 법 위반 내용을 포함한 국외이전 계약 금지 (개인정보 보호법 제28조의8 제5항)"

    validation = validate_grounding(answer, results)

    assert validation["valid"] is True
    assert validation["audit"]["fully_traceable"] is True
    claim = validation["claims"][0]
    assert claim["claim_id"] == "C1"
    assert claim["support_method"] == "explicit_citation"
    assert claim["supporting_citation"] is not None
    assert claim["source_document_id"] is not None
    assert claim["source_excerpt"] is not None


def test_presentation_outline_exposes_rule_and_item_trace_ids():
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline

    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    domain = service.registry.get("digital_business")
    results = service.retriever.retrieve(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain=domain,
        top_k=5,
    )
    plan = build_composition_plan(results, {"actions": ["처리위탁", "국외이전"]})
    outline = build_presentation_outline(plan)

    rule = outline["actions"][0]["rules"][0]
    assert rule["trace_id"].endswith(":lead")
    assert rule["rule_id"].startswith("R")
    assert rule["source_document_id"]
    for item in rule["checklist_evidence"]:
        assert item["trace_id"].startswith(rule["rule_id"] + ":item:")
        assert item["citation"] == rule["citation"]
        assert item["source_text"]


def test_invalid_grounding_at_exact_threshold_uses_evidence_fallback():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.answer import generate_grounded_answer
    from law_rag.generation.providers import DeterministicProvider, GenerationOutput

    class BoundaryProvider(DeterministicProvider):
        def generate(self, prompt):
            supported = [
                "개인정보 보호법 제26조 제1항에 따라 위탁계약은 문서로 작성해야 합니다.",
                "개인정보 보호법 제26조 제5항에 따라 업무 범위를 초과한 이용은 금지됩니다.",
                "개인정보 보호법 제28조의8 제1항에 따라 국외 이전 근거를 확인해야 합니다.",
                "개인정보 보호법 제28조의8 제5항에 따라 위법한 국외이전 계약은 금지됩니다.",
                "개인정보 보호법 제26조 제1항에 따라 보호조치를 계약에 포함해야 합니다.",
                "개인정보 보호법 제28조의8 제1항에 따라 별도 동의를 받을 수 있습니다.",
                "개인정보 보호법 제28조의8 제1항에 따라 처리방침 공개 방식을 확인해야 합니다.",
                "개인정보 보호법 제26조 제5항에 따라 제3자 제공은 제한됩니다.",
            ]
            unsupported = [
                "사업자는 모든 자료를 영구 보관해야 합니다.",
                "모든 위반에는 자동으로 형사처벌이 부과됩니다.",
            ]
            return GenerationOutput(text="\n".join(supported + unsupported), provider="test", model="test")

    results = [
        SearchResult(
            provision=LegalProvision(
                document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
                article_no="제26조", paragraph_no="제1항",
                text="개인정보처리자가 제3자에게 개인정보의 처리 업무를 위탁하는 경우에는 문서로 하여야 한다.",
            ), score=1.0, retrieval_reason="planned",
        ),
        SearchResult(
            provision=LegalProvision(
                document_id="pipa:28-8:1", law_id="011357", law_name="개인정보 보호법",
                article_no="제28조의8", paragraph_no="제1항",
                text="개인정보처리자는 법정 요건에 해당하는 경우 개인정보를 국외로 이전할 수 있다.",
            ), score=0.9, retrieval_reason="planned",
        ),
    ]
    response = generate_grounded_answer(
        "개인정보를 위탁하면서 국외 이전하는 절차는?",
        results,
        BoundaryProvider(),
        legal_intent={"actions": ["처리위탁", "국외이전"]},
    )

    assert response.composition["fallback_used"] is True
    assert response.composition["mode"] == "evidence_fallback"
    assert "실무상 조치" in response.answer
    assert response.grounding_validation["valid"] is True
    assert response.grounding_validation["coverage"] == 1.0


def test_standard_answer_limitations_are_not_scored_as_legal_claims():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.grounding import validate_grounding

    results = [SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보 처리 업무를 위탁하는 경우에는 문서로 하여야 한다.",
        ), score=1.0,
    )]
    answer = "\n".join([
        "개인정보 보호법 제26조 제1항에 따라 위탁계약은 문서로 작성해야 합니다.",
        "본 답변은 제공된 법령 조문에 근거한 일반적인 절차 안내이며, 개별 사건의 구체적 사실관계에 따라 달라질 수 있습니다.",
        "따라서 실제 적용 시에는 관련 법령 전체와 구체적인 상황을 종합적으로 검토할 필요가 있습니다.",
    ])

    validation = validate_grounding(answer, results)

    assert validation["claim_count"] == 1
    assert validation["valid"] is True
    assert validation["coverage"] == 1.0


def test_overseas_transfer_subparagraphs_become_operational_actions():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline, compose_evidence_fallback

    result = SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제28조의8", paragraph_no="제1항",
            text=(
                "개인정보처리자는 개인정보를 국외로 제공·처리위탁·보관하여서는 아니 된다. "
                "다만 다음 각 호의 어느 하나에 해당하는 경우에는 이전할 수 있다.\n"
                "1. 정보주체로부터 국외 이전에 관한 별도의 동의를 받은 경우\n"
                "2. 법률, 대한민국을 당사자로 하는 조약 또는 국제협정에 특별한 규정이 있는 경우\n"
                "3. 정보주체와의 계약의 체결 및 이행을 위하여 처리위탁·보관이 필요한 경우\n"
                "4. 개인정보 보호 인증을 받은 경우로서 필요한 조치를 모두 한 경우\n"
                "5. 보호체계가 실질적으로 동등한 수준이라고 보호위원회가 인정하는 경우"
            ),
        ),
        score=1.0,
        retrieval_reason="planned",
    )
    plan = build_composition_plan([result], {"actions": ["국외이전"]})
    outline = build_presentation_outline(plan)
    rule = outline["actions"][0]["rules"][0]
    answer = compose_evidence_fallback("국외 이전 절차는?", plan)

    assert rule["display_text"] == "적법한 국외이전 근거를 선택·확인"
    assert rule["checklist"] == [
        "국외이전 별도 동의 확보",
        "법률·조약·국제협정상 이전 근거 확인",
        "계약 이행 목적의 위탁·보관 요건 확인",
        "인증받은 이전받는 자와 필수 보호조치 확인",
        "동등 보호수준 인정 국가·국제기구 여부 확인",
    ]
    assert "정보주체와의 계약의 체결 및 이행을 위하여" not in answer
    assert len(rule["source_checklist"]) == 5
    assert all(item["source_text"] for item in rule["checklist_evidence"])


def test_hierarchical_provenance_graph_connects_action_to_sub_provisions():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline

    result = SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제28조의8", paragraph_no="제1항",
            text=(
                "개인정보처리자는 개인정보를 국외로 이전하여서는 아니 된다. "
                "다만 다음 각 호의 어느 하나에 해당하면 이전할 수 있다."
            ),
        ),
        score=1.0,
        retrieval_reason="planned",
        sub_provisions=[
            {
                "document_id": "pipa:28-8:1:1",
                "citation": "개인정보 보호법 제28조의8 제1항 제1호",
                "text": "1. 정보주체로부터 국외 이전에 관한 별도의 동의를 받은 경우",
            },
            {
                "document_id": "pipa:28-8:1:2",
                "citation": "개인정보 보호법 제28조의8 제1항 제2호",
                "text": "2. 법률, 조약 또는 국제협정에 특별한 규정이 있는 경우",
            },
        ],
    )
    plan = build_composition_plan([result], {"actions": ["국외이전"]})
    outline = build_presentation_outline(plan)
    graph = outline["provenance_graph"]
    rule = outline["actions"][0]["rules"][0]

    assert graph["node_count"] == 3
    assert graph["edge_count"] == 2
    assert graph["fully_connected"] is True
    assert len(graph["root_node_ids"]) == 1
    assert len(rule["supporting_node_ids"]) == 3
    assert {row["citation"] for row in rule["supporting_citations"]} >= {
        "개인정보 보호법 제28조의8 제1항 제1호",
        "개인정보 보호법 제28조의8 제1항 제2호",
    }


def test_grounding_claim_exposes_plural_supporting_evidence():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.grounding import validate_grounding

    result = SearchResult(
        provision=LegalProvision(
            document_id="pipa:28-8:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제28조의8", paragraph_no="제1항",
            text="법정 요건에 해당하는 경우 개인정보를 국외로 이전할 수 있다.",
        ),
        score=1.0,
        sub_provisions=[
            {
                "document_id": "pipa:28-8:1:1",
                "citation": "개인정보 보호법 제28조의8 제1항 제1호",
                "text": "1. 정보주체로부터 국외 이전에 관한 별도의 동의를 받은 경우",
            },
            {
                "document_id": "pipa:28-8:1:2",
                "citation": "개인정보 보호법 제28조의8 제1항 제2호",
                "text": "2. 법률, 조약 또는 국제협정에 특별한 규정이 있는 경우",
            },
        ],
    )
    validation = validate_grounding(
        "□ 적법한 국외이전 근거를 선택·확인 (개인정보 보호법 제28조의8 제1항)",
        [result],
    )
    claim = validation["claims"][0]

    assert validation["valid"] is True
    assert len(claim["supporting_citations"]) >= 2
    assert len(claim["supporting_evidence"]) >= 2
    assert validation["audit"]["multi_source_claim_count"] == 1
    assert validation["audit"]["supported_evidence_count"] >= 2


def test_grounding_classifies_evidence_roles_without_dropping_sources():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.grounding import validate_grounding

    act = SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보 처리업무를 위탁하는 경우 문서로 하여야 한다.",
        ),
        score=1.0,
        sub_provisions=[{
            "document_id": "pipa:26:1:1",
            "citation": "개인정보 보호법 제26조 제1항 제1호",
            "text": "1. 위탁업무 수행 목적 외 개인정보 처리 금지에 관한 사항",
        }],
    )
    decree = SearchResult(
        provision=LegalProvision(
            document_id="pipa-decree:26:1", law_id="011468", law_name="개인정보 보호법 시행령",
            article_no="제26조", paragraph_no="제1항",
            text="위탁 문서에는 위탁하는 사무의 목적 및 범위를 포함하여야 한다.",
        ),
        score=0.9,
        sub_provisions=[{
            "document_id": "pipa-decree:26:1:1",
            "citation": "개인정보 보호법 시행령 제26조 제1항 제1호",
            "text": "1. 위탁하는 사무의 목적 및 범위",
        }],
    )
    validation = validate_grounding(
        "□ 위탁 목적 외 개인정보 처리 금지 (개인정보 보호법 제26조 제1항)",
        [act, decree],
    )
    claim = validation["claims"][0]
    roles = {row["citation"]: row["role"] for row in claim["supporting_evidence"]}

    assert len(claim["supporting_evidence"]) == 4
    assert roles["개인정보 보호법 제26조 제1항 제1호"] == "primary"
    assert roles["개인정보 보호법 제26조 제1항"] == "parent"
    assert roles["개인정보 보호법 시행령 제26조 제1항 제1호"] == "implementing_regulation"
    assert roles["개인정보 보호법 시행령 제26조 제1항"] == "implementing_regulation"
    assert validation["audit"]["evidence_role_counts"]["implementing_regulation"] == 2


def test_presentation_provenance_marks_rule_root_as_parent():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.composer import build_composition_plan, build_presentation_outline

    result = SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보 처리업무를 위탁하는 경우 문서로 하여야 한다.",
        ),
        score=1.0,
        sub_provisions=[{
            "document_id": "pipa:26:1:1",
            "citation": "개인정보 보호법 제26조 제1항 제1호",
            "text": "1. 위탁업무 수행 목적 외 개인정보 처리 금지에 관한 사항",
        }],
    )
    outline = build_presentation_outline(
        build_composition_plan([result], {"actions": ["처리위탁"]})
    )
    citations = outline["actions"][0]["rules"][0]["supporting_citations"]

    assert citations[0]["role"] == "parent"
    assert citations[1]["role"] == "primary"


def test_semantic_assignment_separates_direct_and_contextual_sibling_evidence():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.grounding import validate_grounding

    result = SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보 처리업무를 위탁하는 경우 문서로 하여야 한다.",
        ),
        score=1.0,
        sub_provisions=[
            {
                "document_id": "pipa:26:1:1",
                "citation": "개인정보 보호법 제26조 제1항 제1호",
                "text": "1. 위탁업무 수행 목적 외 개인정보 처리 금지에 관한 사항",
            },
            {
                "document_id": "pipa:26:1:2",
                "citation": "개인정보 보호법 제26조 제1항 제2호",
                "text": "2. 개인정보의 기술적·관리적 보호조치에 관한 사항",
            },
        ],
    )
    validation = validate_grounding(
        "□ 위탁 목적 외 개인정보 처리 금지 (개인정보 보호법 제26조 제1항)",
        [result],
    )
    claim = validation["claims"][0]
    rows = {row["citation"]: row for row in claim["supporting_evidence"]}

    assert rows["개인정보 보호법 제26조 제1항 제1호"]["assigned"] is True
    assert rows["개인정보 보호법 제26조 제1항 제1호"]["assignment_reason"] == "primary_semantic_match"
    assert rows["개인정보 보호법 제26조 제1항 제2호"]["assigned"] is False
    assert rows["개인정보 보호법 제26조 제1항 제2호"]["role"] == "contextual"
    assert {row["citation"] for row in claim["assigned_evidence"]} == {
        "개인정보 보호법 제26조 제1항 제1호",
        "개인정보 보호법 제26조 제1항",
    }
    assert "목적 외 처리 금지" in claim["semantic_labels"]


def test_semantic_assignment_only_assigns_matching_implementing_regulation():
    from law_rag.domain.models import LegalProvision, SearchResult
    from law_rag.generation.grounding import validate_grounding

    act = SearchResult(
        provision=LegalProvision(
            document_id="pipa:26:1", law_id="011357", law_name="개인정보 보호법",
            article_no="제26조", paragraph_no="제1항",
            text="개인정보 처리업무를 위탁하는 경우 문서로 하여야 한다.",
        ),
        score=1.0,
        sub_provisions=[{
            "document_id": "pipa:26:1:1",
            "citation": "개인정보 보호법 제26조 제1항 제1호",
            "text": "1. 위탁업무 수행 목적 외 개인정보 처리 금지에 관한 사항",
        }],
    )
    decree = SearchResult(
        provision=LegalProvision(
            document_id="decree:26:1", law_id="011468", law_name="개인정보 보호법 시행령",
            article_no="제26조", paragraph_no="제1항",
            text="위탁 문서에 필요한 사항을 포함하여야 한다.",
        ),
        score=0.9,
        sub_provisions=[
            {
                "document_id": "decree:26:1:1",
                "citation": "개인정보 보호법 시행령 제26조 제1항 제1호",
                "text": "1. 위탁하는 사무의 목적 및 범위",
            },
            {
                "document_id": "decree:26:1:2",
                "citation": "개인정보 보호법 시행령 제26조 제1항 제2호",
                "text": "2. 재위탁 제한에 관한 사항",
            },
        ],
    )
    validation = validate_grounding(
        "□ 위탁 목적과 업무 범위를 계약서에 명시해야 한다 (개인정보 보호법 제26조 제1항)",
        [act, decree],
    )
    claim = validation["claims"][0]
    rows = {row["citation"]: row for row in claim["supporting_evidence"]}

    assert rows["개인정보 보호법 시행령 제26조 제1항 제1호"]["assigned"] is True
    assert rows["개인정보 보호법 시행령 제26조 제1항 제1호"]["role"] == "implementing_regulation"
    assert rows["개인정보 보호법 시행령 제26조 제1항 제2호"]["assigned"] is False
    assert rows["개인정보 보호법 시행령 제26조 제1항 제2호"]["role"] == "contextual"
    assert validation["audit"]["assigned_evidence_count"] >= 1
    assert validation["audit"]["contextual_evidence_count"] >= 1
    assert validation["audit"]["semantic_assignment_coverage"] == 1.0


def test_answer_v16_uses_graph_nodes_as_authoritative_evidence():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer("개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?", domain_id="digital_business", top_k=5)
    graph_ids = [node["document_id"] for node in response["evidence_graph"]["nodes"]]
    assert response["prompt_version"] == "answer_v22"
    assert response["authoritative_evidence_ids"] == graph_ids


def test_answer_v16_repairs_contract_noncompliance():
    from law_rag.generation.providers import GenerationOutput

    class OldFormatProvider(DeterministicProvider):
        def generate(self, prompt):
            return GenerationOutput(
                text="결론\n검토가 필요합니다.\n\n판단 순서\n1. 처리위탁\n\n실무 체크리스트\n- 확인",
                provider="old-format",
                model="test",
            )

    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=OldFormatProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    assert response["prompt_version"] == "answer_v22"
    assert response["composition"]["fallback_used"] is True
    assert response["composition"]["answer_contract_validation"]["valid"] is True
    assert "쟁점별 법적 판단" in response["answer"]
    assert "적용 요건과 예외" in response["answer"]
    assert "실무상 조치" in response["answer"]


def test_answer_v16_serializes_reasoning_steps_and_transitions():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    composition = response["composition"]
    assert response["prompt_version"] == "answer_v22"
    assert composition["planner_enabled"] is True
    assert composition["mode"] == "sentence_plan_bound"
    assert composition["answer_plan"]["source_step_order"] == list(range(1, len(composition["answer_plan"]["source_step_order"]) + 1))
    assert composition["answer_plan"]["transition_count"] >= 1
    assert "처리위탁 과정에서 개인정보가 국외로 이전되는 경우" in response["answer"]
    assert "추가 적용" in response["answer"]
    assert response["answer"].find("개인정보 국외이전") < response["answer"].find("개인정보 처리위탁")


def test_answer_v16_exposes_sentence_level_plan_provenance():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보 수집 동의 요건은?",
        domain_id="digital_business",
        top_k=1,
    )
    sections = response["composition"]["answer_plan"]["sections"]
    sentences = [sentence for section in sections for sentence in section["sentences"]]
    step_sentences = [sentence for sentence in sentences if sentence["source_step"] is not None]
    assert step_sentences
    assert all(sentence["citations"] for sentence in step_sentences)
    assert [sentence["source_step"] for sentence in step_sentences] == sorted(
        sentence["source_step"] for sentence in step_sentences
    )


def test_answer_v16_binds_every_cited_sentence_to_evidence_nodes():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    composition = response["composition"]
    assert composition["sentence_plan_validation"]["valid"] is True
    assert composition["citation_binding_count"] > 0
    sentences = [
        sentence
        for section in composition["answer_plan"]["sections"]
        for sentence in section["sentences"]
    ]
    cited = [sentence for sentence in sentences if sentence["citations"]]
    assert cited
    assert all(sentence["citation_bindings"] for sentence in cited)
    assert all(sentence["rendered_text"] for sentence in sentences)
    assert all(sentence["rendered_hash"] for sentence in sentences)


def test_answer_v16_sentence_plan_matches_final_answer_exactly():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    validation = response["composition"]["sentence_plan_validation"]
    assert validation == {
        "valid": True,
        "sentence_count": validation["sentence_count"],
        "missing_sentence_ids": [],
        "sentence_order_valid": True,
        "unbound_citation_sentence_ids": [],
        "hash_invalid_sentence_ids": [],
    }


def test_answer_v18_verifies_reasoning_steps_transitions_and_issues():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    composition = response["composition"]
    verification = composition["reasoning_verification"]
    assert response["prompt_version"] == "answer_v22"
    assert verification["valid"] is True
    assert verification["missing_steps"] == []
    assert verification["missing_transitions"] == []
    assert verification["missing_issues"] == []
    assert verification["step_coverage"] == 1.0
    assert verification["transition_coverage"] == 1.0


def test_answer_v18_exposes_semantic_citation_coverage_and_score():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    composition = response["composition"]
    coverage = composition["semantic_citation_coverage"]
    score = composition["reasoning_score"]
    report = composition["explainability_report"]
    assert coverage["valid"] is True
    assert coverage["sentence_binding_coverage"] == 1.0
    assert coverage["semantic_grounding_coverage"] == 1.0
    assert score["score"] == 1.0
    assert score["level"] == "high"
    assert report["auditable"] is True
    assert report["sentence_trace"]
    assert all("rendered_hash" in row for row in report["sentence_trace"])


def test_answer_v18_exposes_dual_output_and_trace():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    assert response["prompt_version"] == "answer_v22"
    assert response["dual_output"]["available_modes"] == ["user", "expert"]
    assert response["user_answer"]["mode"] == "user"
    assert response["user_answer"]["summary"]
    assert response["expert_report"]["mode"] == "expert"
    assert response["expert_report"]["auditable"] is True
    assert response["reasoning_trace"]
    assert response["reasoning_trace"][0]["sentence_id"]
    assert response["reasoning_trace"][0]["rendered_hash"]


def test_answer_v18_graph_structure_is_deterministic_and_traceable():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    graph = response["graph_answer_structure"]
    trace = response["reasoning_trace"]
    assert graph["node_count"] == len(trace)
    assert graph["edge_count"] == max(0, graph["node_count"] - 1)
    assert graph["root_node_id"] == trace[0]["sentence_id"]
    assert [node["node_id"] for node in graph["nodes"]] == [row["sentence_id"] for row in trace]
    assert all(edge["relation"] == "followed_by" for edge in graph["edges"])


def test_answer_v22_exposes_legal_logic_tree_validation_and_skeleton():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    tree = response["legal_logic_tree"]
    validation = response["logic_validation"]
    skeleton = response["answer_skeleton"]

    assert response["prompt_version"] == "answer_v22"
    assert tree["enabled"] is True
    assert tree["root_id"] == "logic:root"
    assert {node["node_type"] for node in tree["nodes"]} >= {"issue", "rule", "conclusion"}
    assert validation["valid"] is True
    assert validation["covered_issue_count"] == validation["issue_count"]
    assert skeleton["enabled"] is True
    assert skeleton["section_order"][:3] == ["conclusion", "legal_analysis", "requirements"]
    assert response["expert_report"]["legal_logic_tree"]["root_id"] == "logic:root"
    assert response["expert_report"]["logic_validation"]["valid"] is True


def test_answer_v22_rule_priority_places_exceptions_before_primary_and_supporting():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    rows = response["rule_priority"]
    role_rank = {"exception": 0, "primary": 1, "supporting": 2}
    ranks = [role_rank.get(row["role"], 3) for row in rows]
    assert ranks == sorted(ranks)
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))


def test_answer_v22_uses_logic_tree_as_planner_reasoning_source():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    path = response["logic_driven_reasoning_path"]
    tree_node_ids = {node["node_id"] for node in response["legal_logic_tree"]["nodes"]}
    assert response["prompt_version"] == "answer_v22"
    assert path["source"] == "legal_logic_tree"
    assert path["complete"] is True
    assert all(
        step.get("source_logic_node_id") in tree_node_ids
        for step in path["steps"]
        if step["type"] != "identify_issue"
    )
    assert response["expert_report"]["logic_driven_reasoning_path"]["source"] == "legal_logic_tree"
    assert response["composition"]["answer_plan"]["source_step_order"] == [
        step["step"] for step in path["steps"]
    ]


def test_answer_v22_exposes_source_bound_counter_reasoning():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    counter = response["counter_reasoning"]
    assert counter["enabled"] is True
    assert counter["source_bound"] is True
    assert counter["candidate_count"] >= 2
    assert any(row["selected"] == "limited_interpretation" for row in counter["candidates"])
    assert all(row["citations"] for row in counter["candidates"])
    assert response["expert_report"]["counter_reasoning"] == counter


def test_answer_v22_resolves_rule_competition_before_planning():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    competition = response["rule_competition"]
    resolution = response["conflict_resolution"]
    path = response["logic_driven_reasoning_path"]
    assert competition["enabled"] is True
    assert competition["competition_count"] >= 2
    assert resolution["enabled"] is True
    assert resolution["resolved_count"] == resolution["decision_count"]
    assert any(row["resolution_type"] == "exception_controls" for row in resolution["decisions"])
    decision_steps = [step for step in path["steps"] if step["type"] == "resolve_rule_conflict"]
    assert len(decision_steps) == resolution["conflict_count"]
    assert all(step["source_decision_id"] for step in decision_steps)


def test_answer_v22_exposes_auditable_decision_trace():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    trace = response["decision_trace"]
    assert response["prompt_version"] == "answer_v22"
    assert trace["enabled"] is True
    assert trace["trace_count"] >= 2
    assert any(
        step["action"] == "rejected_as_unqualified"
        for row in trace["traces"]
        for step in row["steps"]
    )
    assert response["expert_report"]["rule_competition"] == response["rule_competition"]
    assert response["expert_report"]["conflict_resolution"] == response["conflict_resolution"]
    assert response["expert_report"]["decision_trace"] == trace


def test_answer_v22_composer_exposes_irac_roles_and_sentence_citations():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    composer = response["answer_composer"]
    citation_map = response["sentence_citation_map"]
    assert composer["enabled"] is True
    assert composer["framework"] == "FRAC"
    assert composer["role_counts"]["rule"] > 0
    assert composer["role_counts"]["application"] > 0
    assert composer["role_counts"]["conclusion"] > 0
    assert citation_map["valid"] is True
    assert citation_map["fully_bound_count"] == citation_map["citation_required_count"]
    assert response["expert_report"]["answer_composer"] == composer
    assert response["expert_report"]["sentence_citation_map"] == citation_map


def test_answer_v22_missing_fact_detector_is_concrete_and_issue_scoped():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    detector = response["missing_fact_detector"]
    fact_ids = {row["fact_id"] for row in detector["facts"]}
    assert detector["enabled"] is True
    assert detector["missing_fact_count"] >= 5
    assert {"delegation_purpose", "transfer_country", "transfer_basis"} <= fact_ids
    assert all(row["question"].endswith("?") for row in detector["facts"])
    assert {row["issue_id"] for row in detector["facts"]} >= {"processing_delegation", "cross_border_transfer"}
    assert "이전 국가" in response["answer"]


def test_answer_v22_practical_actions_replace_generic_action_text():
    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains", llm_provider=DeterministicProvider())
    response = service.answer(
        "개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
        domain_id="digital_business",
        top_k=5,
    )
    generator = response["practical_action_generator"]
    action_ids = [row["action_id"] for row in generator["actions"]]
    assert generator["enabled"] is True
    assert generator["source_bound"] is True
    assert generator["action_count"] >= 4
    assert "document_delegation" in action_ids
    assert "select_transfer_basis" in action_ids
    assert all(row["citations"] for row in generator["actions"])
    practical_section = next(
        section for section in response["composition"]["answer_plan"]["sections"]
        if section["section_id"] == "practical_actions"
    )
    assert any("위탁계약 문서화" in row["text"] for row in practical_section["sentences"])
    assert any("국외이전 근거 확정" in row["text"] for row in practical_section["sentences"])
