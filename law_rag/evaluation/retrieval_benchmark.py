from __future__ import annotations

import json
import math
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Protocol

from law_rag import __version__
from law_rag.domain.config import DomainRegistry
from law_rag.domain.models import LegalProvision
from law_rag.evaluation.datasets import dataset_snapshot, sha256_file
from law_rag.evaluation.runner import EvaluationCase, load_dataset
from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.retrieval.bm25 import BM25Retriever
from law_rag.retrieval.embedding import DEFAULT_EMBEDDING_MODEL, SentenceTransformerEmbeddingRetriever
from law_rag.retrieval.hybrid import HybridRetriever
from law_rag.retrieval.reranker import (
    DEFAULT_RERANKER_MODEL,
    CrossEncoderProvisionReranker,
    ProvisionReranker,
)
from law_rag.retrieval.semantic import CharNgramSemanticRetriever


class ScoreRetriever(Protocol):
    def score(self, query: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class RetrievalBenchmarkConfig:
    dataset_path: str = "evaluation/datasets/official_core_cases.json"
    corpus_path: str = "data/legal_corpus.json"
    domains_path: str = "domains"
    methods: tuple[str, ...] = ("bm25", "semantic_lite", "hybrid")
    top_k: int = 5
    seed: int = 42
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    fine_tuned_embedding_model: str | None = None
    reranker_model: str = DEFAULT_RERANKER_MODEL
    retrieval_top_n: int = 20
    query_rewrite: bool = True


def is_retrieval_case(case: EvaluationCase) -> bool:
    """Keep gold-bearing answerable cases; safety/abstention belongs elsewhere."""
    has_gold = bool(case.expected_document_ids or case.uses_article_expectation)
    return has_gold and not case.expected_abstain


def _is_in_force(provision: LegalProvision, case: EvaluationCase) -> bool:
    if case.as_of_date is None:
        return provision.is_current
    if provision.effective_from and provision.effective_from > case.as_of_date:
        return False
    if provision.effective_to and provision.effective_to < case.as_of_date:
        return False
    return True


def _candidates(
    provisions: list[LegalProvision], case: EvaluationCase, registry: DomainRegistry
) -> list[LegalProvision]:
    domain = registry.get(case.domain)
    return [
        row for row in provisions
        if _is_in_force(row, case)
        and (domain is None or row.law_name in domain.laws or domain.domain_id in row.domain_tags)
    ]


def _identity(provision: LegalProvision, case: EvaluationCase) -> str:
    if case.uses_article_expectation:
        return f"{provision.law_id}:{provision.article_no}"
    return provision.document_id


def _gold(case: EvaluationCase) -> set[str]:
    if case.uses_article_expectation:
        return {f"{case.expected_law_id}:{article}" for article in case.expected_article_nos or []}
    return set(case.expected_document_ids or [])


def _metrics(ranked: list[str], expected: set[str]) -> dict[str, float | bool]:
    matched = expected.intersection(ranked)
    first_rank = next((rank for rank, value in enumerate(ranked, 1) if value in expected), None)
    dcg = sum(1.0 / math.log2(rank + 1) for rank, value in enumerate(ranked, 1) if value in expected)
    ideal_hits = min(len(expected), len(ranked))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return {
        "top1_hit": bool(ranked and ranked[0] in expected),
        "hit_at_k": bool(matched),
        "recall_at_k": len(matched) / len(expected) if expected else 0.0,
        "reciprocal_rank": 1.0 / first_rank if first_rank else 0.0,
        "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


class RetrievalBenchmarkRunner:
    supported_methods = {
        "bm25", "semantic_lite", "hybrid", "pretrained_embedding", "fine_tuned_embedding",
        "semantic_lite_reranker", "hybrid_reranker", "pretrained_embedding_reranker",
        "fine_tuned_embedding_reranker",
    }

    def __init__(
        self,
        config: RetrievalBenchmarkConfig,
        *,
        embedding_model_instance: Any | None = None,
        fine_tuned_embedding_model_instance: Any | None = None,
        reranker: ProvisionReranker | None = None,
    ) -> None:
        unknown = set(config.methods) - self.supported_methods
        if unknown:
            raise ValueError(f"unsupported benchmark methods: {', '.join(sorted(unknown))}")
        if config.top_k < 1:
            raise ValueError("top_k must be at least 1")
        if config.retrieval_top_n < config.top_k:
            raise ValueError("retrieval_top_n must be greater than or equal to top_k")
        if any(method.startswith("fine_tuned_embedding") for method in config.methods) and not config.fine_tuned_embedding_model:
            raise ValueError("fine_tuned_embedding_model is required for fine-tuned methods")
        self.config = config
        self.provisions = JsonLegalDocumentSource().load(config.corpus_path)
        self.registry = DomainRegistry(config.domains_path).load_all()
        self.embedding_model_instance = embedding_model_instance
        self.fine_tuned_embedding_model_instance = fine_tuned_embedding_model_instance
        self.reranker = reranker
        self._score_retrievers: dict[tuple[str, tuple[str, ...]], ScoreRetriever] = {}
        self._index_build_ms: dict[str, float] = {}

    @staticmethod
    def _candidate_key(candidates: list[LegalProvision]) -> tuple[str, ...]:
        return tuple(row.document_id for row in candidates)

    def _prepare_retriever(self, method: str, candidates: list[LegalProvision]) -> None:
        key = (method, self._candidate_key(candidates))
        if method == "hybrid" or key in self._score_retrievers:
            return
        started = time.perf_counter()
        if method == "bm25":
            retriever: ScoreRetriever = BM25Retriever(candidates)
        elif method == "semantic_lite":
            retriever = CharNgramSemanticRetriever(candidates)
        elif method == "pretrained_embedding":
            retriever = SentenceTransformerEmbeddingRetriever(
                candidates,
                model_name=self.config.embedding_model,
                model=self.embedding_model_instance,
            )
            if self.embedding_model_instance is None:
                self.embedding_model_instance = retriever.model
        else:
            retriever = SentenceTransformerEmbeddingRetriever(
                candidates,
                model_name=str(self.config.fine_tuned_embedding_model),
                model=self.fine_tuned_embedding_model_instance,
            )
            if self.fine_tuned_embedding_model_instance is None:
                self.fine_tuned_embedding_model_instance = retriever.model
        self._score_retrievers[key] = retriever
        elapsed = (time.perf_counter() - started) * 1000
        self._index_build_ms[method] = round(self._index_build_ms.get(method, 0.0) + elapsed, 3)

    def _rank_scored(
        self, method: str, query: str, candidates: list[LegalProvision]
    ) -> list[LegalProvision]:
        self._prepare_retriever(method, candidates)
        key = (method, self._candidate_key(candidates))
        scores = self._score_retrievers[key].score(query)
        ranked = sorted(
            zip(candidates, scores),
            key=lambda row: row[1],
            reverse=True,
        )
        return [row for row, _ in ranked]

    def _rank(self, method: str, case: EvaluationCase) -> list[LegalProvision]:
        candidates = _candidates(self.provisions, case, self.registry)
        domain = self.registry.get(case.domain)
        if method == "hybrid":
            return [
                result.provision for result in HybridRetriever(candidates).retrieve(
                    case.question,
                    domain=domain,
                    top_k=min(len(candidates), self.config.retrieval_top_n),
                    as_of_date=case.as_of_date,
                    include_related=False,
                    strategy="hybrid",
                    query_rewrite=self.config.query_rewrite,
                )
            ]
        query = (
            HybridRetriever.expand_query(case.question, domain)
            if self.config.query_rewrite else case.question
        )
        return self._rank_scored(method, query, candidates)

    @staticmethod
    def _base_method(method: str) -> str:
        return method.removesuffix("_reranker")

    def _get_reranker(self) -> ProvisionReranker:
        if self.reranker is None:
            self.reranker = CrossEncoderProvisionReranker(model_name=self.config.reranker_model)
        return self.reranker

    def _run_method(self, method: str, cases: list[EvaluationCase]) -> dict[str, Any]:
        base_method = self._base_method(method)
        uses_reranker = method.endswith("_reranker")
        if base_method != "hybrid":
            for case in cases:
                self._prepare_retriever(base_method, _candidates(self.provisions, case, self.registry))
        rows: list[dict[str, Any]] = []
        for case in cases:
            retrieval_started = time.perf_counter()
            provisions = self._rank(base_method, case)[: self.config.retrieval_top_n]
            retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000
            reranking_latency_ms = 0.0
            reranker_scores: list[dict[str, Any]] = []
            if uses_reranker:
                reranking_started = time.perf_counter()
                reranked = self._get_reranker().rerank(case.question, provisions, top_k=self.config.top_k)
                reranking_latency_ms = (time.perf_counter() - reranking_started) * 1000
                provisions = [item.provision for item in reranked]
                reranker_scores = [
                    {"document_id": item.provision.document_id, "score": round(item.score, 6), "original_rank": item.original_rank}
                    for item in reranked
                ]
            latency_ms = retrieval_latency_ms + reranking_latency_ms
            ranked = list(dict.fromkeys(_identity(row, case) for row in provisions))[: self.config.top_k]
            metrics = _metrics(ranked, _gold(case))
            rows.append({
                "case_id": case.case_id,
                "question": case.question,
                "domain": case.domain,
                "category": case.category,
                "expected": sorted(_gold(case)),
                "retrieved": ranked,
                **{key: round(float(value), 6) if not isinstance(value, bool) else value for key, value in metrics.items()},
                "latency_ms": round(latency_ms, 3),
                "retrieval_latency_ms": round(retrieval_latency_ms, 3),
                "reranking_latency_ms": round(reranking_latency_ms, 3),
                "reranker_scores": reranker_scores,
            })
        return {
            "method": method,
            "model": (
                self.config.fine_tuned_embedding_model if base_method == "fine_tuned_embedding"
                else self.config.embedding_model if base_method == "pretrained_embedding" else None
            ),
            "reranker_model": self.config.reranker_model if uses_reranker else None,
            "retrieval_top_n": self.config.retrieval_top_n if uses_reranker else None,
            "case_count": len(rows),
            "index_build_ms": self._index_build_ms.get(base_method),
            "latency_scope": (
                "end_to_end_dynamic_candidate_index"
                if base_method == "hybrid" else "query_only_after_index_build"
            ),
            "metrics": {
                "top1_accuracy": round(mean(row["top1_hit"] for row in rows), 6),
                "hit_at_k": round(mean(row["hit_at_k"] for row in rows), 6),
                "mean_recall_at_k": round(mean(row["recall_at_k"] for row in rows), 6),
                "mrr": round(mean(row["reciprocal_rank"] for row in rows), 6),
                "ndcg_at_k": round(mean(row["ndcg_at_k"] for row in rows), 6),
                "average_latency_ms": round(mean(row["latency_ms"] for row in rows), 3),
                "average_retrieval_latency_ms": round(mean(row["retrieval_latency_ms"] for row in rows), 3),
                "average_reranking_latency_ms": round(mean(row["reranking_latency_ms"] for row in rows), 3),
            },
            "cases": rows,
        }

    def run(self) -> dict[str, Any]:
        all_cases = load_dataset(self.config.dataset_path)
        cases = [case for case in all_cases if is_retrieval_case(case)]
        snapshot = dataset_snapshot(self.config.dataset_path, case_count=len(all_cases))
        return {
            "benchmark_id": f"retrieval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "code_version": __version__,
            "dataset": snapshot,
            "corpus": {
                "path": self.config.corpus_path,
                "content_sha256": sha256_file(self.config.corpus_path),
                "provision_count": len(self.provisions),
            },
            "config": asdict(self.config),
            "selection": {
                "policy": "gold_bearing_non_abstention_cases",
                "selected_case_count": len(cases),
                "excluded_case_count": len(all_cases) - len(cases),
            },
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "results": [self._run_method(method, cases) for method in self.config.methods],
        }


def write_retrieval_benchmark(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
