from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import re
from time import perf_counter

from law_rag import __version__
from law_rag.confidence import score_confidence
from law_rag.domain.config import DomainRegistry
from law_rag.generation.answer import generate_grounded_answer
from law_rag.generation.analysis import (
    build_answer_structure,
    build_related_provisions,
    build_retrieval_explanation,
)
from law_rag.generation.prompt import build_grounded_prompt
from law_rag.generation.providers import LlmProvider, provider_from_env
from law_rag.generation.citations import normalize_citation_label
from law_rag.generation.composer import build_composition_plan
from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.observability import JsonlRunLogger
from law_rag.retrieval.aggregation import aggregate_evidence
from law_rag.retrieval.hybrid import HybridRetriever
from law_rag.retrieval.ontology_filter import (
    rerank_with_ontology,
    ensure_compound_concept_coverage,
    filter_graph_evidence,
    annotate_ontology_metadata,
)
from law_rag.retrieval.evidence_graph import build_evidence_graph
from law_rag.reasoning import LawGraph, ReasoningChainBuilder
from law_rag.planning import LegalIntentPlanner


class LawRagService:
    def __init__(
        self,
        data_path: str | Path = "data/legal_corpus.json",
        domains_path: str | Path = "domains",
        llm_provider: LlmProvider | None = None,
    ) -> None:
        self.data_path = Path(data_path)
        self.domains_path = Path(domains_path)
        self.provisions = JsonLegalDocumentSource().load(self.data_path)
        self.registry = DomainRegistry(self.domains_path).load_all()
        self.retriever = HybridRetriever(self.provisions)
        self.law_graph = LawGraph(self.provisions)
        self.reasoning_builder = ReasoningChainBuilder()
        self.intent_planner = LegalIntentPlanner()
        self.llm_provider = llm_provider or provider_from_env()
        self.run_logger = JsonlRunLogger()
        self.corpus_version = self._corpus_version()

    def _planned_raw_results(
        self,
        question: str,
        *,
        domain,
        requested_top_k: int,
        as_of_date: date | None,
    ):
        plan = self.intent_planner.plan(question)
        candidate_limit = max(requested_top_k * 6, 30)
        if not plan.is_compound:
            # Single-issue questions still benefit from planner expansions (especially
            # definition questions whose surface wording is sparse). Retrieve with the
            # original wording plus action-specific statutory anchors, then constrain.
            expanded_query = " ".join(plan.subqueries)
            raw = self.retriever.retrieve(
                expanded_query, domain=domain, top_k=candidate_limit, as_of_date=as_of_date
            )
            return plan, rerank_with_ontology(question, plan, raw)

        # Reciprocal-rank fusion gives every independently detected legal act a fair
        # retrieval path, while retaining the original full-question search.
        fused: dict[str, object] = {}
        fusion_scores: dict[str, float] = {}
        anchored_articles: set[str] = set()
        for query_index, subquery in enumerate(plan.subqueries):
            weight = 1.15 if query_index == 0 else 1.0
            anchors = set(re.findall(r"제\d+조(?:의\d+)?", subquery))
            anchored_articles.update(anchors)
            subresults = self.retriever.retrieve(
                subquery, domain=domain, top_k=candidate_limit, as_of_date=as_of_date
            )
            for rank, result in enumerate(subresults, start=1):
                document_id = result.provision.document_id
                anchor_bonus = 0.055 if result.provision.article_no in anchors else 0.0
                fusion_scores[document_id] = fusion_scores.get(document_id, 0.0) + weight / (20 + rank) + anchor_bonus
                current = fused.get(document_id)
                if current is None or result.score > current.score:
                    fused[document_id] = result

        if not fused:
            return plan, []
        peak = max(fusion_scores.values()) or 1.0
        merged = []
        for document_id, result in fused.items():
            rrf = fusion_scores[document_id] / peak
            anchor_signal = 1.0 if result.provision.article_no in anchored_articles else 0.0
            result.score = result.score * 0.50 + rrf * 0.40 + anchor_signal * 0.10
            result.retrieval_reason = "planned"
            merged.append(result)
        merged = rerank_with_ontology(question, plan, merged)
        merged = ensure_compound_concept_coverage(plan, merged, limit=candidate_limit)
        return plan, merged

    def retrieve(
        self,
        question: str,
        *,
        domain_id: str | None = None,
        top_k: int | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, object]:
        normalized_question = question.strip()
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        plan, raw_results = self._planned_raw_results(
            normalized_question, domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date
        )
        # Aggregation creates article/paragraph-level evidence units. Re-run the
        # ontology pass on those final units so ontology metadata is not stale or
        # lost, then exclude nodes that cannot connect to a requested issue.
        aggregated = aggregate_evidence(raw_results, self.provisions, limit=max(requested_top_k * 3, requested_top_k))
        results = annotate_ontology_metadata(plan, aggregated)
        results = filter_graph_evidence(plan, results)[:requested_top_k]
        for rank, result in enumerate(results, 1):
            result.rank = rank
        evidence_graph = build_evidence_graph(plan, results)
        return {
            "question": normalized_question,
            "domain": domain_id or "all",
            "results": [self._serialize_result(result) for result in results],
            "abstain": (not results) or ((not evidence_graph.get("issues")) and (not results or results[0].score < 0.80)),
            "evidence_status": self._evidence_status(results),
            "legal_intent": plan.to_dict(),
            "evidence_graph": evidence_graph,
            "legal_reasoning_path": evidence_graph.get("reasoning_path", {}),
        }

    def query(
        self,
        question: str,
        *,
        domain_id: str | None = None,
        top_k: int | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, object]:
        started = perf_counter()
        response = self.retrieve(
            question,
            domain_id=domain_id,
            top_k=top_k,
            as_of_date=as_of_date,
        )
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        _, raw_results = self._planned_raw_results(
            str(response["question"]), domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date
        )
        results = aggregate_evidence(raw_results, self.provisions, limit=requested_top_k)
        expanded = self.law_graph.expand(results, limit=max(3, len(results)))
        reasoning_chain = self.reasoning_builder.build(results, expanded)
        reasoning_path = response.get("legal_reasoning_path", {})
        graph_ids = [str(node.get("document_id")) for node in response.get("evidence_graph", {}).get("nodes", [])]
        candidates = {row.provision.document_id: row for row in [*results, *expanded]}
        authoritative_results = [candidates[doc_id] for doc_id in graph_ids if doc_id in candidates]
        if not authoritative_results:
            authoritative_results = results
        for rank, row in enumerate(authoritative_results, 1):
            row.rank = rank
        composition_plan = build_composition_plan(authoritative_results, response.get("legal_intent"))
        response["prompt"] = build_grounded_prompt(str(response["question"]), authoritative_results, reasoning_chain=reasoning_chain, legal_intent=response.get("legal_intent"), composition_plan=composition_plan, legal_reasoning_path=reasoning_path)
        response["authoritative_evidence_ids"] = [row.provision.document_id for row in authoritative_results]
        response["prompt_version"] = "answer_v22"
        response["reasoning_chain"] = reasoning_chain
        response["graph_expansion"] = self._serialize_graph_expansion(expanded)
        response["metadata"] = self._metadata(started)
        return response


    def answer(
        self,
        question: str,
        *,
        domain_id: str | None = None,
        top_k: int | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, object]:
        started = perf_counter()
        response = self.retrieve(
            question,
            domain_id=domain_id,
            top_k=top_k,
            as_of_date=as_of_date,
        )
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        _, raw_results = self._planned_raw_results(
            str(response["question"]), domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date
        )
        results = aggregate_evidence(raw_results, self.provisions, limit=requested_top_k)
        expanded = self.law_graph.expand(results, limit=max(3, len(results)))
        reasoning_chain = self.reasoning_builder.build(results, expanded)
        reasoning_path = response.get("legal_reasoning_path", {})
        graph_ids = [str(node.get("document_id")) for node in response.get("evidence_graph", {}).get("nodes", [])]
        candidates = {row.provision.document_id: row for row in [*results, *expanded]}
        reasoning_results = [candidates[doc_id] for doc_id in graph_ids if doc_id in candidates]
        if not reasoning_results:
            reasoning_results = results
        for rank, row in enumerate(reasoning_results, 1):
            row.rank = rank
        generation_results = [] if response.get("abstain") else reasoning_results
        generated = generate_grounded_answer(
            str(response["question"]),
            generation_results,
            self.llm_provider,
            reasoning_chain=reasoning_chain,
            legal_intent=response.get("legal_intent"),
            legal_reasoning_path=reasoning_path,
        )
        response.update(
            {
                "answer": generated.answer,
                "generation_status": generated.generation_status,
                "provider": generated.provider,
                "model": generated.model,
                "citation_validation": generated.citation_validation,
                "grounding_validation": generated.grounding_validation,
                "composition": generated.composition,
                "dual_output": generated.composition.get("dual_output", {}),
                "user_answer": generated.composition.get("dual_output", {}).get("user", {}),
                "expert_report": generated.composition.get("dual_output", {}).get("expert", {}),
                "reasoning_trace": generated.composition.get("reasoning_trace", []),
                "graph_answer_structure": generated.composition.get("graph_answer_structure", {}),
                "legal_logic_tree": generated.composition.get("legal_logic_tree", {}),
                "logic_validation": generated.composition.get("logic_validation", {}),
                "answer_skeleton": generated.composition.get("answer_skeleton", {}),
                "rule_priority": generated.composition.get("rule_priority", []),
                "counter_reasoning": generated.composition.get("counter_reasoning", {}),
                "rule_competition": generated.composition.get("rule_competition", {}),
                "conflict_resolution": generated.composition.get("conflict_resolution", {}),
                "decision_trace": generated.composition.get("decision_trace", {}),
                "logic_driven_reasoning_path": generated.composition.get("logic_driven_reasoning_path", {}),
                "answer_composer": generated.composition.get("answer_composer", {}),
                "sentence_citation_map": generated.composition.get("sentence_citation_map", {}),
                "missing_fact_detector": generated.composition.get("missing_fact_detector", {}),
                "practical_action_generator": generated.composition.get("practical_action_generator", {}),
                "legal_argument_graph": generated.composition.get("legal_argument_graph", {}),
                "multi_path_reasoning": generated.composition.get("multi_path_reasoning", {}),
                "generation_error": generated.error,
                "generation_request_id": generated.request_id,
                "generation_usage": generated.usage,
                "prompt_version": "answer_v22",
                "authoritative_evidence_ids": [row.provision.document_id for row in reasoning_results],
                "reasoning_chain": reasoning_chain,
                "graph_expansion": self._serialize_graph_expansion(expanded),
                "answer_structure": build_answer_structure(str(response["question"]), results),
                "related_provisions": build_related_provisions(results),
                "retrieval_explanation": build_retrieval_explanation(results),
                "confidence": score_confidence(
                    reasoning_results,
                    generated.citation_validation.get("valid"),
                    float(generated.grounding_validation.get("coverage", 0.0)),
                ),
                "metadata": self._metadata(started),
            }
        )
        self.run_logger.write({
            "question": response["question"],
            "domain": response["domain"],
            "result_count": len(results),
            "generation_status": generated.generation_status,
            "provider": generated.provider,
            "model": generated.model,
            "generation_request_id": generated.request_id,
            "generation_usage": generated.usage,
            "confidence": response["confidence"],
            "latency_ms": response["metadata"]["latency_ms"],
        })
        return response

    def list_domains(self) -> list[dict[str, object]]:
        return [
            {
                "domain_id": config.domain_id,
                "display_name": config.display_name,
                "laws": list(config.laws),
                "default_top_k": config.retrieval.top_k,
            }
            for config in self.registry.list()
        ]

    def list_laws(self, *, domain_id: str | None = None) -> list[dict[str, object]]:
        domain = self.registry.get(domain_id)
        allowed_laws = set(domain.laws) if domain else None
        grouped = defaultdict(list)
        for provision in self.provisions:
            if allowed_laws is not None and provision.law_name not in allowed_laws:
                continue
            grouped[(provision.law_id, provision.law_name, provision.document_type)].append(provision)

        laws = []
        for (law_id, law_name, document_type), provisions in grouped.items():
            effective_dates = sorted(
                provision.effective_from
                for provision in provisions
                if provision.effective_from is not None
            )
            laws.append(
                {
                    "law_id": law_id,
                    "law_name": law_name,
                    "document_type": document_type,
                    "provision_count": len(provisions),
                    "content_kinds": sorted({p.content_kind for p in provisions}),
                    "effective_from_min": effective_dates[0].isoformat() if effective_dates else None,
                    "effective_from_max": effective_dates[-1].isoformat() if effective_dates else None,
                }
            )
        return sorted(laws, key=lambda item: (str(item["law_name"]), str(item["law_id"])))

    def _corpus_version(self) -> str:
        versions = sorted({p.version_id for p in self.provisions if p.version_id})
        return ",".join(versions) if versions else "unknown"

    def _metadata(self, started: float) -> dict[str, object]:
        return {
            "service_version": __version__,
            "corpus_version": self.corpus_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
        }

    @staticmethod
    def _serialize_result(result) -> dict[str, object]:
        return {
            "rank": result.rank,
            "score": round(result.score, 4),
            "lexical_score": round(result.lexical_score, 4),
            "semantic_score": round(result.semantic_score, 4),
            "citation": normalize_citation_label(result.provision.citation_label()),
            "document_id": result.provision.document_id,
            "law_id": result.provision.law_id,
            "article_no": result.provision.article_no,
            "evidence_scope": result.evidence_scope,
            "sub_provisions": result.sub_provisions,
            "text": result.provision.text,
            "content_kind": result.provision.content_kind,
            "source_url": result.provision.source_url,
            "retrieval_reason": result.retrieval_reason,
            "relation_score": round(result.relation_score, 4),
            "version_id": result.provision.version_id,
            "matched_signals": {
                "lexical": round(result.lexical_score, 4),
                "semantic": round(result.semantic_score, 4),
                "relation": round(result.relation_score, 4),
                "title": round(result.title_score, 4),
                "coverage": round(result.coverage_score, 4),
                "ontology": round(result.ontology_score, 4),
                "issue_coverage": round(result.issue_coverage_score, 4),
            },
            "evidence_role": result.evidence_role,
            "issue_ids": result.issue_ids,
            "effective_from": (
                result.provision.effective_from.isoformat()
                if result.provision.effective_from else None
            ),
        }


    @staticmethod
    def _serialize_graph_expansion(results) -> dict[str, object]:
        return {
            "enabled": True,
            "expanded_count": len(results),
            "results": [
                {
                    "citation": normalize_citation_label(result.provision.citation_label()),
                    "document_id": result.provision.document_id,
                    "law_id": result.provision.law_id,
                    "article_no": result.provision.article_no,
                    "relation": result.retrieval_reason,
                    "relation_score": round(result.relation_score, 4),
                }
                for result in results
            ],
        }

    @staticmethod
    def _evidence_status(results):
        if not results:
            return {"level": "insufficient", "message": "검색 근거가 없습니다."}
        direct = [r for r in results if r.retrieval_reason == "direct"]
        if len(direct) == 1 and len(results) == 1:
            return {
                "level": "partial",
                "message": "단일 조문만 검색되어 관련 요건이 누락될 수 있습니다.",
            }
        return {
            "level": "usable",
            "message": "직접 검색 근거와 관련 조문을 함께 확보했습니다.",
        }
