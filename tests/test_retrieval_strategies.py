import pytest

from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.retrieval.hybrid import HybridRetriever


def test_lexical_semantic_and_hybrid_are_real_selectable_modes():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")
    retriever = HybridRetriever(provisions)
    outputs = {
        strategy: retriever.retrieve("개인정보 수집 동의", top_k=3, strategy=strategy)
        for strategy in ("lexical", "semantic", "hybrid")
    }
    assert all(outputs.values())
    assert all(row.semantic_score >= 0 for row in outputs["lexical"])
    assert all(row.lexical_score >= 0 for row in outputs["semantic"])


def test_invalid_strategy_is_rejected():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")
    with pytest.raises(ValueError):
        HybridRetriever(provisions).retrieve("질문", strategy="invented")
