from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
import re
from time import perf_counter

from law_rag import __version__
from law_rag.confidence import score_confidence
from law_rag.domain.config import DomainRegistry
from law_rag.domain.models import SearchResult
from law_rag.generation.answer import generate_grounded_answer
from law_rag.generation.display_answer import build_display_answer
from law_rag.generation.precedent_answer import (
    generate_precedent_grounded_answer,
    validate_precedent_evidence,
)
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
from law_rag.retrieval.precedent import PrecedentRetriever
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
        precedent_data_path: str | Path = "data/precedent_poc.json",
    ) -> None:
        self.data_path = Path(data_path)
        self.domains_path = Path(domains_path)
        self.provisions = JsonLegalDocumentSource().load(self.data_path)
        self.registry = DomainRegistry(self.domains_path).load_all()
        self.retriever = HybridRetriever(self.provisions)
        self.precedent_retriever = PrecedentRetriever(precedent_data_path)
        self.law_graph = LawGraph(self.provisions)
        self.reasoning_builder = ReasoningChainBuilder()
        self.intent_planner = LegalIntentPlanner()
        self.llm_provider = llm_provider or provider_from_env()
        self.run_logger = JsonlRunLogger()
        self.corpus_version = self._corpus_version()

    def _matched_domain_query_paths(self, question: str):
        """Build reusable domain-specific search paths from explicit query signals.

        The router does not predict a legal conclusion or inject a gold article. It
        reuses the public domain configurations: an alias or a query-rule trigger
        must be present in the question before that path can participate.
        """
        lowered = question.lower()
        matched = []
        for config in self.registry.list():
            paths: list[str] = []
            for canonical, aliases in config.aliases.items():
                terms = [str(canonical), *(str(alias) for alias in aliases)]
                if any(term.lower() in lowered for term in terms):
                    paths.append(" ".join([question, canonical, *aliases]))
            for rule in config.query_rules:
                all_terms = [str(term).lower() for term in rule.get("all", [])]
                any_terms = [str(term).lower() for term in rule.get("any", [])]
                if all_terms and not all(term in lowered for term in all_terms):
                    continue
                if any_terms and not any(term in lowered for term in any_terms):
                    continue
                expansions = [str(term) for term in rule.get("expand", [])]
                if expansions:
                    paths.append(" ".join([question, *expansions]))
            deduped = list(dict.fromkeys(paths))
            if deduped:
                matched.append((config, deduped))
        return matched

    def _domain_routed_raw_results(
        self,
        question: str,
        *,
        requested_top_k: int,
        as_of_date: date | None,
        search_strategy: str = "hybrid",
        query_rewrite: bool = True,
    ):
        routes = self._matched_domain_query_paths(question)
        if not routes:
            return None

        candidate_limit = max(requested_top_k * 6, 30)
        fused: dict[str, SearchResult] = {}
        fusion_scores: dict[str, float] = defaultdict(float)
        route_leader_counts: dict[str, int] = defaultdict(int)
        route_count = 0
        for config, queries in routes:
            for route_query in queries:
                route_count += 1
                results = self.retriever.retrieve(
                    route_query,
                    domain=config,
                    top_k=candidate_limit,
                    as_of_date=as_of_date,
                    strategy=search_strategy,
                    query_rewrite=query_rewrite,
                )
                for rank, result in enumerate(results, start=1):
                    document_id = result.provision.document_id
                    fusion_scores[document_id] += 1.0 / (20 + rank)
                    if rank <= 2:
                        route_leader_counts[document_id] += 1
                    current = fused.get(document_id)
                    if current is None or result.score > current.score:
                        fused[document_id] = result

        if not fused:
            return None
        peak = max(fusion_scores.values()) or 1.0
        normalized_route_count = max(route_count, 1)
        merged = []
        for document_id, result in fused.items():
            rrf = fusion_scores[document_id] / peak
            route_leadership = min(1.0, route_leader_counts[document_id] / normalized_route_count * 2.0)
            result.score = min(0.995, result.score * 0.48 + rrf * 0.37 + route_leadership * 0.15)
            result.retrieval_reason = "domain_routed"
            # A positive relation score records an explicit configured route and
            # prevents an unrelated single-domain ontology filter from deleting it.
            result.relation_score = max(result.relation_score, 0.05)
            merged.append(result)
        merged.sort(key=lambda row: (row.score, row.semantic_score, row.lexical_score), reverse=True)
        for rank, result in enumerate(merged, start=1):
            result.rank = rank
        return merged[:candidate_limit]

    def _planned_raw_results(
        self,
        question: str,
        *,
        domain,
        requested_top_k: int,
        as_of_date: date | None,
        search_strategy: str = "hybrid",
        query_rewrite: bool = True,
        reranking: bool = True,
    ):
        plan = self.intent_planner.plan(question)
        candidate_limit = max(requested_top_k * 6, 30)
        if domain is None:
            routed = self._domain_routed_raw_results(
                question,
                requested_top_k=requested_top_k,
                as_of_date=as_of_date,
                search_strategy=search_strategy,
                query_rewrite=query_rewrite,
            )
            if routed is not None:
                # The default ontology currently covers privacy concepts most
                # deeply. Applying it as a global reranker here would suppress
                # valid finance or IP routes in the same question. Metadata is
                # still annotated after aggregation, while explicit route
                # provenance keeps each configured domain path auditable.
                return plan, routed
        if not plan.is_compound:
            # Single-issue questions still benefit from planner expansions (especially
            # definition questions whose surface wording is sparse). Retrieve with the
            # original wording plus action-specific statutory anchors, then constrain.
            expanded_query = " ".join(plan.subqueries) if query_rewrite else question
            raw = self.retriever.retrieve(
                expanded_query, domain=domain, top_k=candidate_limit, as_of_date=as_of_date,
                strategy=search_strategy, query_rewrite=query_rewrite,
            )
            return plan, rerank_with_ontology(question, plan, raw) if reranking else raw

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
                subquery, domain=domain, top_k=candidate_limit, as_of_date=as_of_date,
                strategy=search_strategy, query_rewrite=query_rewrite,
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
        if reranking:
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
        search_strategy: str = "hybrid",
        query_rewrite: bool = True,
        reranking: bool = True,
    ) -> dict[str, object]:
        normalized_question = question.strip()
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        plan, raw_results = self._planned_raw_results(
            normalized_question, domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date,
            search_strategy=search_strategy, query_rewrite=query_rewrite, reranking=reranking,
        )
        # Aggregation creates article/paragraph-level evidence units. Re-run the
        # ontology pass on those final units so ontology metadata is not stale or
        # lost, then exclude nodes that cannot connect to a requested issue.
        aggregated = aggregate_evidence(raw_results, self.provisions, limit=max(requested_top_k * 3, requested_top_k))
        results = annotate_ontology_metadata(plan, aggregated)
        results = filter_graph_evidence(plan, results)[:requested_top_k]
        allowed_laws = set(domain.laws) if domain else None
        precedent = self.precedent_retriever.retrieve(
            normalized_question, top_k=min(3, requested_top_k), allowed_laws=allowed_laws
        )
        precedent_validation = validate_precedent_evidence(precedent["results"])
        statute_precedent_alignment = self._statute_precedent_alignment(
            results, precedent["results"], precedent_validation
        )
        precedent_linked_results = []
        if statute_precedent_alignment["checked"] and not statute_precedent_alignment["aligned"]:
            precedent_linked_results = self._precedent_linked_results(
                precedent["results"], precedent_validation, as_of_date=as_of_date
            )
            linked_keys = {
                (row.provision.law_id, row.provision.article_no.replace(" ", ""))
                for row in precedent_linked_results
            }
            results = [
                *precedent_linked_results,
                *[
                    row for row in results
                    if (row.provision.law_id, row.provision.article_no.replace(" ", "")) not in linked_keys
                ],
            ][:requested_top_k]
        for rank, result in enumerate(results, 1):
            result.rank = rank
        evidence_graph = build_evidence_graph(plan, results)
        # Ontology가 쟁점을 명시적으로 포착하지 못하더라도 검색 점수가 충분히
        # 높으면 답변 생성을 허용한다. 기존 0.80 임계값은 조문 표현과 질문 표현이
        # 다른 정상 질의까지 과도하게 유보했다. 0.70 미만의 저신뢰 후보는 계속
        # 답변 근거로 채택하지 않는다.
        statute_abstain = (not results) or (
            (not evidence_graph.get("issues"))
            and results[0].score < 0.70
        )
        if statute_precedent_alignment["checked"] and not statute_precedent_alignment["aligned"]:
            statute_abstain = True
        precedent_supported = bool(precedent_validation["answer_supported"])
        abstain = statute_abstain and not precedent_supported
        if abstain:
            evidence_status = self._evidence_status(results, abstain=True)
        elif statute_abstain and precedent_supported:
            evidence_status = {
                "level": "partial",
                "message": "직접 법령 검색은 제한적이지만 공식 판례의 검증 요약이 질문의 해석 쟁점을 충분히 뒷받침합니다.",
            }
        else:
            evidence_status = self._evidence_status(results, abstain=False)
        return {
            "question": normalized_question,
            "domain": domain_id or "all",
            "results": [self._serialize_result(result) for result in results],
            "abstain": abstain,
            "evidence_status": evidence_status,
            "legal_intent": plan.to_dict(),
            "evidence_graph": evidence_graph,
            "legal_reasoning_path": evidence_graph.get("reasoning_path", {}),
            "precedent_evidence": precedent["results"],
            "precedent_validation": precedent_validation,
            "evidence_routing": {
                "statute": True,
                "precedent": bool(precedent["routed"]),
                "precedent_reason": precedent["reason"],
                "statute_sufficient": not statute_abstain,
                "answer_basis": "precedent" if statute_abstain and precedent_supported else "statute",
                "statute_precedent_alignment": statute_precedent_alignment,
                "precedent_linked_statutes": [
                    {
                        "document_id": row.provision.document_id,
                        "law_id": row.provision.law_id,
                        "law_name": row.provision.law_name,
                        "article_no": row.provision.article_no,
                    }
                    for row in precedent_linked_results
                ],
            },
        }

    def _precedent_linked_results(
        self,
        precedents,
        validation,
        *,
        as_of_date: date | None,
    ) -> list[SearchResult]:
        """Materialize verified precedent-to-statute links from the local corpus.

        Only substantive provisions already present in the official corpus are
        returned. These rows are provenance-labelled and never presented as
        ordinary lexical/semantic hits.
        """
        qualified = set(map(str, validation.get("qualified_precedent_ids", [])))
        primary = next(
            (row for row in precedents if str(row.get("precedent_id")) in qualified),
            None,
        )
        if not primary:
            return []
        precedent_score = float(primary.get("score", 0.0))
        output: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        for link in primary.get("related_statutes", []):
            law_id = str(link.get("law_id", ""))
            article_no = str(link.get("article_no", "")).replace(" ", "")
            key = (law_id, article_no)
            if not law_id or not article_no or key in seen:
                continue
            seen.add(key)
            matches = [
                provision for provision in self.provisions
                if provision.law_id == law_id
                and provision.article_no.replace(" ", "") == article_no
                and len(re.sub(r"\s+", "", provision.text)) >= 20
                and (
                    as_of_date is None
                    or (
                        (provision.effective_from is None or provision.effective_from <= as_of_date)
                        and (provision.effective_to is None or as_of_date <= provision.effective_to)
                    )
                )
            ]
            if not matches:
                continue
            matches.sort(key=lambda provision: (
                provision.paragraph_no or "",
                provision.item_no or "",
                provision.subitem_no or "",
            ))
            representative = matches[0]
            text_parts: list[str] = []
            for provision in matches:
                text = provision.text.strip()
                if text and text not in text_parts:
                    text_parts.append(text)
            merged = replace(
                representative,
                document_id=f"{law_id}:{article_no}",
                paragraph_no=None,
                item_no=None,
                subitem_no=None,
                text="\n".join(text_parts),
            )
            output.append(SearchResult(
                provision=merged,
                score=precedent_score,
                lexical_score=0.0,
                semantic_score=0.0,
                retrieval_reason="precedent_linked",
                relation_score=precedent_score,
                evidence_scope="article",
                sub_provisions=[
                    {
                        "document_id": provision.document_id,
                        "citation": provision.citation_label(),
                        "text": provision.text,
                    }
                    for provision in matches
                ],
                evidence_role="contextual",
            ))
        return output

    @staticmethod
    def _statute_precedent_alignment(results, precedents, validation) -> dict[str, object]:
        """Check whether statute Top-1 matches the verified precedent's statute links.

        A mismatch does not delete retrieval output. It prevents those candidates
        from being promoted to direct normative evidence when a verified precedent
        provides a more specific issue-to-statute mapping.
        """
        qualified = set(map(str, validation.get("qualified_precedent_ids", [])))
        primary = next(
            (row for row in precedents if str(row.get("precedent_id")) in qualified),
            None,
        )
        linked = [] if not primary else [
            {
                "law_id": str(item.get("law_id", "")),
                "law_name": str(item.get("law_name", "")),
                "article_no": str(item.get("article_no", "")).replace(" ", ""),
            }
            for item in primary.get("related_statutes", [])
            if item.get("law_id") and item.get("article_no")
        ]
        if not results or not linked:
            return {
                "checked": False,
                "aligned": True,
                "top1": None,
                "precedent_id": str(primary.get("precedent_id")) if primary else None,
                "linked_statutes": linked,
                "reason": "검증 판례 또는 연결 조문이 없어 정합성 가드를 적용하지 않았습니다.",
            }
        top = results[0].provision
        top_key = (str(top.law_id), str(top.article_no).replace(" ", ""))
        aligned = any((item["law_id"], item["article_no"]) == top_key for item in linked)
        return {
            "checked": True,
            "aligned": aligned,
            "top1": {
                "law_id": str(top.law_id),
                "law_name": str(top.law_name),
                "article_no": str(top.article_no).replace(" ", ""),
            },
            "precedent_id": str(primary.get("precedent_id")),
            "linked_statutes": linked,
            "reason": (
                "법령 Top-1이 검증 판례의 연결 조문과 일치합니다."
                if aligned else
                "법령 Top-1이 검증 판례의 연결 조문과 불일치하여 법령 결과를 검색 후보로 강등했습니다."
            ),
        }

    def query(
        self,
        question: str,
        *,
        domain_id: str | None = None,
        top_k: int | None = None,
        as_of_date: date | None = None,
        search_strategy: str = "hybrid",
        query_rewrite: bool = True,
        reranking: bool = True,
    ) -> dict[str, object]:
        started = perf_counter()
        response = self.retrieve(
            question,
            domain_id=domain_id,
            top_k=top_k,
            as_of_date=as_of_date,
            search_strategy=search_strategy,
            query_rewrite=query_rewrite,
            reranking=reranking,
        )
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        _, raw_results = self._planned_raw_results(
            str(response["question"]), domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date,
            search_strategy=search_strategy, query_rewrite=query_rewrite, reranking=reranking,
        )
        results = aggregate_evidence(raw_results, self.provisions, limit=requested_top_k)
        expanded = self.law_graph.expand(results, limit=max(3, len(results)))
        reasoning_path = response.get("legal_reasoning_path", {})
        graph_nodes = {
            str(node.get("document_id")): node
            for node in response.get("evidence_graph", {}).get("nodes", [])
        }
        linked = self._precedent_linked_results(
            response.get("precedent_evidence", []),
            response.get("precedent_validation", {}),
            as_of_date=as_of_date,
        )
        candidates = {row.provision.document_id: row for row in [*results, *expanded, *linked]}
        for document_id, node in graph_nodes.items():
            if document_id in candidates:
                candidates[document_id].evidence_role = str(node.get("role", "candidate"))
        authoritative_results = [
            candidates[document_id] for document_id, node in graph_nodes.items()
            if document_id in candidates and node.get("role") != "candidate"
        ]
        if not authoritative_results:
            authoritative_results = [row for row in results if row.evidence_role != "candidate"] or results
        for rank, row in enumerate(authoritative_results, 1):
            row.rank = rank
        reasoning_chain = self.reasoning_builder.build(authoritative_results, [])
        composition_plan = build_composition_plan(authoritative_results, response.get("legal_intent"))
        response["prompt"] = build_grounded_prompt(str(response["question"]), authoritative_results, reasoning_chain=reasoning_chain, legal_intent=response.get("legal_intent"), composition_plan=composition_plan, legal_reasoning_path=reasoning_path)
        if not response.get("abstain"):
            response["results"] = [self._serialize_result(row) for row in authoritative_results]
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
        search_strategy: str = "hybrid",
        query_rewrite: bool = True,
        reranking: bool = True,
    ) -> dict[str, object]:
        started = perf_counter()
        response = self.retrieve(
            question,
            domain_id=domain_id,
            top_k=top_k,
            as_of_date=as_of_date,
            search_strategy=search_strategy,
            query_rewrite=query_rewrite,
            reranking=reranking,
        )
        domain = self.registry.get(domain_id)
        requested_top_k = top_k or (domain.retrieval.top_k if domain else 5)
        _, raw_results = self._planned_raw_results(
            str(response["question"]), domain=domain, requested_top_k=requested_top_k, as_of_date=as_of_date,
            search_strategy=search_strategy, query_rewrite=query_rewrite, reranking=reranking,
        )
        results = aggregate_evidence(raw_results, self.provisions, limit=requested_top_k)
        expanded = self.law_graph.expand(results, limit=max(3, len(results)))
        reasoning_path = response.get("legal_reasoning_path", {})
        graph_nodes = {
            str(node.get("document_id")): node
            for node in response.get("evidence_graph", {}).get("nodes", [])
        }
        linked = self._precedent_linked_results(
            response.get("precedent_evidence", []),
            response.get("precedent_validation", {}),
            as_of_date=as_of_date,
        )
        candidates = {row.provision.document_id: row for row in [*results, *expanded, *linked]}
        for document_id, node in graph_nodes.items():
            if document_id in candidates:
                candidates[document_id].evidence_role = str(node.get("role", "candidate"))
        reasoning_results = [
            candidates[document_id] for document_id, node in graph_nodes.items()
            if document_id in candidates and node.get("role") != "candidate"
        ]
        if not reasoning_results:
            reasoning_results = [row for row in results if row.evidence_role != "candidate"] or results
        for rank, row in enumerate(reasoning_results, 1):
            row.rank = rank
        reasoning_chain = self.reasoning_builder.build(reasoning_results, [])
        precedent_only = (
            response.get("evidence_routing", {}).get("answer_basis") == "precedent"
            and response.get("precedent_validation", {}).get("answer_supported") is True
        )
        if precedent_only:
            generated = generate_precedent_grounded_answer(
                response.get("precedent_evidence", []),
                response.get("precedent_validation", {}),
            )
        else:
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
                "display_answer": build_display_answer(
                    generated.answer,
                    generated.composition,
                    precedents=response.get("precedent_evidence", []),
                    precedent_only=precedent_only,
                ),
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
                "conditional_review": generated.composition.get("conditional_review", {}),
                "legal_argument_graph": generated.composition.get("legal_argument_graph", {}),
                "multi_path_reasoning": generated.composition.get("multi_path_reasoning", {}),
                "generation_error": generated.error,
                "generation_request_id": generated.request_id,
                "generation_usage": generated.usage,
                "prompt_version": "answer_v22",
                "authoritative_evidence_ids": [row.provision.document_id for row in reasoning_results],
                "reasoning_chain": reasoning_chain,
                "graph_expansion": self._serialize_graph_expansion(expanded),
                "answer_structure": build_answer_structure(str(response["question"]), reasoning_results),
                "related_provisions": build_related_provisions(reasoning_results),
                "retrieval_explanation": build_retrieval_explanation(reasoning_results),
                "confidence": self._answer_confidence(
                    reasoning_results,
                    generated,
                    response.get("precedent_evidence", []),
                    precedent_only=precedent_only,
                ),
                "metadata": self._metadata(started),
            }
        )
        if not response.get("abstain"):
            response["results"] = [self._serialize_result(row) for row in reasoning_results]
        reasoning_gate = self._reasoning_safety_gate(response.get("multi_path_reasoning", {}))
        if reasoning_gate is not None:
            safe_answer = (
                "결론\n"
                "- 추론 경로 검증에서 중대한 불일치가 감지되어 확정 답변을 유보합니다.\n\n"
                "추가 확인 사실\n"
                "- 쟁점 분해와 적용 근거를 다시 확인한 뒤 답변을 재실행해야 합니다."
            )
            composition = dict(response.get("composition", {}))
            composition["safety_gate"] = reasoning_gate
            response.update({
                "abstain": True,
                "evidence_status": {
                    "level": "insufficient",
                    "message": "추론 무결성 검증을 통과하지 못해 답변을 유보했습니다.",
                },
                "answer": safe_answer,
                "display_answer": safe_answer,
                "generation_status": "abstained",
                "citation_validation": {
                    "valid": True,
                    "cited_articles": [],
                    "retrieved_articles": sorted({row.provision.article_no for row in reasoning_results}),
                    "unsupported_articles": [],
                },
                "grounding_validation": {
                    "valid": True,
                    "claim_count": 0,
                    "supported_claim_count": 0,
                    "coverage": 1.0,
                    "unsupported_claims": [],
                    "claims": [],
                },
                "composition": composition,
                "confidence": {
                    "score": 0.0,
                    "level": "low",
                    "reasons": ["reasoning_integrity_failure", "answer_abstained"],
                    "components": {
                        "retrieval": 0.0,
                        "coverage": 0.0,
                        "citation": 0.0,
                        "grounding": 0.0,
                    },
                },
            })
        self.run_logger.write({
            "question": response["question"],
            "domain": response["domain"],
            "result_count": len(results),
            "generation_status": response["generation_status"],
            "provider": generated.provider,
            "model": generated.model,
            "generation_request_id": generated.request_id,
            "generation_usage": generated.usage,
            "confidence": response["confidence"],
            "safety_gate": reasoning_gate,
            "latency_ms": response["metadata"]["latency_ms"],
        })
        return response

    @staticmethod
    def _reasoning_safety_gate(multi_path: object) -> dict[str, object] | None:
        if not isinstance(multi_path, dict) or not multi_path.get("enabled"):
            return None
        if int(multi_path.get("path_count", 0) or 0) <= 0:
            return None
        validation = multi_path.get("validation") or {}
        failure = multi_path.get("failure_analysis") or {}
        consistency = multi_path.get("consistency_report") or {}
        reasons: list[str] = []
        if isinstance(validation, dict) and validation.get("valid") is False:
            reasons.append("multi_path_validation_failed")
        if isinstance(failure, dict) and failure.get("status") == "blocked":
            primary = failure.get("primary_failure") or {}
            failure_type = primary.get("failure_type") if isinstance(primary, dict) else None
            if failure_type in {"no_recommended_path", "reasoning_graph_integrity"}:
                reasons.append("critical_reasoning_failure")
        if isinstance(consistency, dict) and consistency.get("consistent") is False:
            reasons.append("reasoning_consistency_failed")
        if not reasons:
            return None
        return {
            "blocked": True,
            "reasons": reasons,
            "pre_gate_failure_status": failure.get("status") if isinstance(failure, dict) else None,
            "pre_gate_validation_valid": validation.get("valid") if isinstance(validation, dict) else None,
            "pre_gate_consistency": consistency.get("consistent") if isinstance(consistency, dict) else None,
        }

    @staticmethod
    def _answer_confidence(reasoning_results, generated, precedents, *, precedent_only: bool):
        if generated.generation_status == "abstained":
            return {
                "score": 0.0,
                "level": "low",
                "reasons": ["answer_abstained", "insufficient_evidence"],
                "components": {"retrieval": 0.0, "coverage": 0.0, "citation": 0.0, "grounding": 0.0},
            }
        if not precedent_only:
            return score_confidence(
                reasoning_results,
                generated.citation_validation.get("valid"),
                float(generated.grounding_validation.get("coverage", 0.0)),
            )
        top_score = float(precedents[0].get("score", 0.0)) if precedents else 0.0
        value = round(min(0.79, 0.45 + top_score * 0.4), 4)
        return {
            "score": value,
            "level": "medium" if value >= 0.55 else "low",
            "reasons": ["verified_precedent", "official_source", "statute_retrieval_limited"],
            "components": {
                "retrieval": round(top_score, 4),
                "coverage": 1.0,
                "citation": 1.0,
                "grounding": 1.0,
            },
        }

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
    def _evidence_status(results, *, abstain: bool = False):
        if not results:
            return {"level": "insufficient", "message": "검색 근거가 없습니다."}
        if abstain:
            return {
                "level": "insufficient",
                "message": "관련 후보 조문은 검색했지만 답변 근거로 채택할 만큼 충분히 일치하지 않습니다.",
            }
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
