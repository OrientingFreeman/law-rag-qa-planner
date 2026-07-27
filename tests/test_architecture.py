from datetime import date

from law_rag.domain.config import DomainRegistry
from law_rag.generation.citations import validate_citations
from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.retrieval.hybrid import HybridRetriever


def test_legacy_json_is_normalized():
    provisions = JsonLegalDocumentSource().load("data/sample_laws.json")
    assert provisions[0].paragraph_no is None
    assert provisions[0].effective_from == date(2023, 1, 1)
    assert provisions[0].document_id


def test_domain_filter_and_hybrid_retrieval():
    provisions = JsonLegalDocumentSource().load("data/sample_laws.json")
    registry = DomainRegistry("domains").load_all()
    results = HybridRetriever(provisions).retrieve(
        "개인정보 수집 동의 요건",
        domain=registry.get("digital_business"),
        top_k=3,
    )
    assert results
    assert results[0].provision.law_name == "개인정보 보호법"


def test_domain_without_loaded_laws_abstains():
    provisions = JsonLegalDocumentSource().load("data/sample_laws.json")
    registry = DomainRegistry("domains").load_all()
    results = HybridRetriever(provisions).retrieve(
        "해고는 며칠 전에 알려야 하나요?",
        domain=registry.get("labor"),
    )
    assert results == []


def test_citation_validator_rejects_unsupported_article():
    provisions = JsonLegalDocumentSource().load("data/sample_laws.json")
    results = HybridRetriever(provisions).retrieve("불법행위 손해배상", top_k=1)
    validation = validate_citations("민법 제999조에 따르면 그렇다.", results)
    assert validation["valid"] is False
    assert "제999조" in validation["unsupported_articles"]


def test_related_provisions_are_expanded():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")
    registry = DomainRegistry("domains").load_all()
    results = HybridRetriever(provisions).retrieve(
        "개인정보 수집 동의 요건",
        domain=registry.get("digital_business"),
        top_k=1,
    )
    ids = {r.provision.document_id for r in results}
    assert "pipa:15:1" in ids or "pipa:15:2" in ids
    assert len(results) > 1


def test_as_of_date_excludes_future_provision():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")
    registry = DomainRegistry("domains").load_all()
    results = HybridRetriever(provisions).retrieve(
        "전자금융 거래기록 보존",
        domain=registry.get("electronic_finance"),
        as_of_date=date(2026, 7, 24),
    )
    assert results == []


def test_official_xml_parser_normalizes_article_paragraph_and_item():
    from law_rag.ingestion.official_source import OfficialKoreanLawSource

    provisions = OfficialKoreanLawSource().load_file(
        "tests/fixtures/sample_law.xml", domain_id="test_domain"
    )
    assert len(provisions) == 2
    assert provisions[0].law_name == "테스트법"
    assert provisions[0].article_no == "제1조"
    assert provisions[0].paragraph_no == "제1항"
    assert provisions[0].content_kind == "official_text"
    assert provisions[1].item_no == "제1호"


def test_related_provision_has_query_and_relation_scores():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")
    registry = DomainRegistry("domains").load_all()
    results = HybridRetriever(provisions).retrieve(
        "개인정보 수집 동의 요건",
        domain=registry.get("digital_business"),
        top_k=1,
    )
    related = [r for r in results if r.retrieval_reason == "related"]
    assert related
    assert all(r.relation_score > 0 for r in related)
    assert any(r.semantic_score > 0 or r.lexical_score > 0 for r in related)


def test_official_api_resolves_name_and_fetches_body_without_persisting_oc():
    from pathlib import Path
    from law_rag.ingestion.official_source import OfficialKoreanLawSource

    search_payload = Path("tests/fixtures/official_law_search.xml").read_bytes()
    body_payload = Path("tests/fixtures/official_law_body.xml").read_bytes()
    requested_urls = []

    def transport(url, timeout):
        requested_urls.append(url)
        return search_payload if "lawSearch.do" in url else body_payload

    source = OfficialKoreanLawSource(transport=transport)
    record, provisions = source.fetch_by_name(
        law_name="개인정보 보호법",
        domain_id="digital_business",
        oc="secret@example.com",
    )
    assert record.law_id == "011357"
    assert provisions[0].law_id == "011357"
    assert any(p.item_no == "제1호" for p in provisions)
    assert any(p.subitem_no == "가" for p in provisions)
    assert any(p.article_no == "제15조의2" for p in provisions)
    assert all("secret%40example.com" not in (p.source_url or "") for p in provisions)
    assert all("OC=" not in (p.source_url or "") for p in provisions)
    assert any("target=law" in url for url in requested_urls)
    assert any("target=eflaw" in url for url in requested_urls)


def test_official_api_exact_name_resolution_rejects_similar_only():
    from pathlib import Path
    import pytest
    from law_rag.ingestion.official_source import OfficialKoreanLawSource, OfficialLawApiError

    payload = Path("tests/fixtures/official_law_search.xml").read_bytes()
    source = OfficialKoreanLawSource(transport=lambda url, timeout: payload)
    with pytest.raises(OfficialLawApiError):
        source.resolve_law(law_name="개인정보 보호법 시행령", oc="secret")


def test_official_list_question_is_aggregated_to_paragraph_scope():
    from law_rag.service import LawRagService

    service = LawRagService(data_path="data/legal_corpus.json", domains_path="domains")
    response = service.retrieve(
        "개인정보 처리방침에는 어떤 내용을 포함해야 하나?",
        domain_id="digital_business",
        top_k=5,
    )
    first = response["results"][0]
    assert first["citation"] == "개인정보 보호법 제30조 제1항"
    assert first["evidence_scope"] == "paragraph"
    assert len(first["sub_provisions"]) >= 4
    assert "개인정보의 처리 목적" in first["text"]
    assert len({(item["law_id"], item["article_no"], item["citation"]) for item in response["results"]}) == len(response["results"])
