import json
from pathlib import Path

import pytest

from law_rag.evaluation.retrieval_benchmark import (
    RetrievalBenchmarkConfig,
    RetrievalBenchmarkRunner,
    _metrics,
    write_retrieval_benchmark,
)
from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.retrieval.embedding import SentenceTransformerEmbeddingRetriever
from law_rag.retrieval.reranker import CrossEncoderProvisionReranker
from tools.run_retrieval_benchmark import main


class FakeEmbeddingModel:
    def encode(self, texts, **kwargs):
        return [
            [float("개인정보" in text), float("근로" in text), float(len(text) > 20)]
            for text in texts
        ]


class FakeCrossEncoder:
    def predict(self, pairs, **kwargs):
        return [10.0 if "제15조" in document else float(index) for index, (_, document) in enumerate(pairs)]


def test_binary_relevance_metrics_include_ndcg():
    metrics = _metrics(["irrelevant", "gold-b", "gold-a"], {"gold-a", "gold-b"})
    assert metrics["top1_hit"] is False
    assert metrics["hit_at_k"] is True
    assert metrics["recall_at_k"] == 1.0
    assert metrics["reciprocal_rank"] == 0.5
    assert 0.69 < metrics["ndcg_at_k"] < 0.7


def test_embedding_retriever_uses_injected_sentence_transformer_interface():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")[:3]
    retriever = SentenceTransformerEmbeddingRetriever(
        provisions, model_name="fake-model", model=FakeEmbeddingModel()
    )
    scores = retriever.score("개인정보를 처리할 수 있는 요건")
    assert len(scores) == len(provisions)
    assert all(-1.0 <= score <= 1.0 for score in scores)


def test_benchmark_separates_retrieval_cases_and_records_versions(tmp_path: Path):
    config = RetrievalBenchmarkConfig(
        dataset_path="evaluation/datasets/official_core_cases.json",
        corpus_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        methods=("bm25", "semantic_lite"),
        top_k=5,
    )
    report = RetrievalBenchmarkRunner(config).run()

    assert report["selection"] == {
        "policy": "gold_bearing_non_abstention_cases",
        "selected_case_count": 45,
        "excluded_case_count": 16,
    }
    assert report["dataset"]["dataset_version"] == "2.0.0"
    assert report["corpus"]["content_sha256"]
    assert {row["method"] for row in report["results"]} == {"bm25", "semantic_lite"}
    for result in report["results"]:
        assert set(result["metrics"]) == {
            "top1_accuracy", "hit_at_k", "mean_recall_at_k", "mrr", "ndcg_at_k",
            "average_latency_ms", "average_retrieval_latency_ms", "average_reranking_latency_ms",
        }
        assert result["index_build_ms"] is not None
        assert result["latency_scope"] == "query_only_after_index_build"

    output = write_retrieval_benchmark(report, tmp_path / "benchmark.json")
    assert json.loads(output.read_text(encoding="utf-8"))["selection"]["selected_case_count"] == 45


def test_pretrained_embedding_benchmark_runs_with_injected_model():
    config = RetrievalBenchmarkConfig(
        dataset_path="evaluation/datasets/official_core_cases.json",
        corpus_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        methods=("pretrained_embedding",),
        embedding_model="fake-model",
    )
    report = RetrievalBenchmarkRunner(
        config, embedding_model_instance=FakeEmbeddingModel()
    ).run()
    result = report["results"][0]
    assert result["method"] == "pretrained_embedding"
    assert result["model"] == "fake-model"


def test_cross_encoder_reranker_changes_only_top_n_order_stably():
    provisions = JsonLegalDocumentSource().load("tests/fixtures/legal_corpus.json")[:4]
    reranker = CrossEncoderProvisionReranker(model_name="fake-reranker", model=FakeCrossEncoder())
    ranked = reranker.rerank("개인정보 처리 근거", provisions, top_k=3)
    assert len(ranked) == 3
    assert ranked[0].score >= ranked[1].score
    assert {row.provision.document_id for row in ranked}.issubset(row.document_id for row in provisions)


def test_benchmark_records_separate_reranker_latency_and_scores():
    config = RetrievalBenchmarkConfig(
        dataset_path="evaluation/datasets/official_core_cases.json",
        corpus_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        methods=("pretrained_embedding_reranker",),
        embedding_model="fake-embedding",
        reranker_model="fake-reranker",
        top_k=5,
        retrieval_top_n=8,
    )
    report = RetrievalBenchmarkRunner(
        config,
        embedding_model_instance=FakeEmbeddingModel(),
        reranker=CrossEncoderProvisionReranker(model_name="fake-reranker", model=FakeCrossEncoder()),
    ).run()
    result = report["results"][0]
    assert result["method"] == "pretrained_embedding_reranker"
    assert result["reranker_model"] == "fake-reranker"
    assert result["retrieval_top_n"] == 8
    assert result["metrics"]["average_reranking_latency_ms"] >= 0
    assert result["cases"][0]["reranker_scores"]


def test_reranker_disabled_preserves_existing_ranking():
    base = RetrievalBenchmarkConfig(
        dataset_path="evaluation/datasets/official_core_cases.json",
        corpus_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        methods=("pretrained_embedding",),
        embedding_model="fake-model",
    )
    first = RetrievalBenchmarkRunner(base, embedding_model_instance=FakeEmbeddingModel()).run()
    second = RetrievalBenchmarkRunner(base, embedding_model_instance=FakeEmbeddingModel()).run()
    assert [row["retrieved"] for row in first["results"][0]["cases"]] == [
        row["retrieved"] for row in second["results"][0]["cases"]
    ]
    assert first["results"][0]["metrics"]["average_reranking_latency_ms"] == 0.0


def test_fine_tuned_method_requires_checkpoint_path():
    with pytest.raises(ValueError, match="fine_tuned_embedding_model"):
        RetrievalBenchmarkRunner(RetrievalBenchmarkConfig(methods=("fine_tuned_embedding",)))


def test_benchmark_rejects_unknown_method():
    with pytest.raises(ValueError, match="unsupported benchmark methods"):
        RetrievalBenchmarkRunner(RetrievalBenchmarkConfig(methods=("dense-ish",)))


def test_cli_returns_failure_when_retrieval_regresses(tmp_path: Path):
    exit_code = main([
        "--corpus", "tests/fixtures/legal_corpus.json",
        "--methods", "bm25",
        "--output", str(tmp_path / "report.json"),
        "--fail-under-hit-at-k", "1.0",
    ])
    assert exit_code == 1
