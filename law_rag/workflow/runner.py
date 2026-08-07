from __future__ import annotations

from datetime import date
from time import perf_counter
from uuid import uuid4

from law_rag.service import LawRagService

from .models import AgentRun, TraceStep, WorkflowConfig, utc_now
from .policy import post_generation, post_retrieval, preflight
from .store import InMemoryTraceStore


STEPS = (
    ("query_analysis", "질의 분석"),
    ("search_strategy", "검색 전략 결정"),
    ("evidence_retrieval", "근거 검색"),
    ("evidence_validation", "근거 적합성 검증"),
    ("reasoning_path", "쟁점 및 적용 경로 구성"),
    ("answer_generation", "답변 생성"),
    ("citation_validation", "인용·근거 검증"),
    ("quality_decision", "품질 판정"),
    ("retry_control", "제한된 재시도"),
    ("finalization", "최종 답변 또는 보류"),
)


class AgentWorkflowRunner:
    def __init__(self, service: LawRagService, store: InMemoryTraceStore | None = None) -> None:
        self.service = service
        self.store = store or InMemoryTraceStore()

    @staticmethod
    def _step(run: AgentRun, step_id: str) -> TraceStep:
        return next(row for row in run.execution_trace if row.step_id == step_id)

    def _record(self, run: AgentRun, step_id: str, action, *, input_summary=None) -> object:
        step = self._step(run, step_id)
        step.status = "running"
        step.started_at = utc_now()
        step.input_summary = input_summary or {}
        started = perf_counter()
        try:
            value = action()
            step.status = "completed"
            return value
        except Exception as exc:
            step.status = "failed"
            step.failure_reason = type(exc).__name__
            raise
        finally:
            step.duration_ms = round((perf_counter() - started) * 1000, 3)
            step.ended_at = utc_now()
            self.store.save(run)

    def run(self, question: str, *, domain_id: str = "all", top_k: int | None = None,
            as_of_date: date | None = None, config: WorkflowConfig | None = None) -> AgentRun:
        config = config or WorkflowConfig()
        run = AgentRun(
            run_id=f"run_{uuid4().hex}", question=question.strip(), domain=domain_id,
            config=config, execution_trace=[TraceStep(step_id=a, step_name=b) for a, b in STEPS],
        )
        self.store.save(run)
        requested_top_k = top_k or 5
        try:
            intent = self._record(run, "query_analysis", lambda: self.service.intent_planner.plan(run.question))
            query_step = self._step(run, "query_analysis")
            query_step.output_summary = {"is_compound": intent.is_compound, "subquery_count": len(intent.subqueries)}

            decision = preflight(run.question, self.service.provisions, as_of_date)
            strategy = self._record(run, "search_strategy", lambda: {
                "strategy": config.search_strategy, "query_rewrite": config.query_rewrite,
                "ontology_reranking": config.reranking,
                "top_k": requested_top_k,
            })
            strategy_step = self._step(run, "search_strategy")
            strategy_step.output_summary = strategy
            strategy_step.search_strategy = config.search_strategy
            if decision.action != "continue":
                strategy_step.status = "warning"
                strategy_step.warnings = decision.warnings
                return self._finish_early(run, decision.reason or "safety_policy", decision.action)

            retrieval = self._record(run, "evidence_retrieval", lambda: self.service.retrieve(
                run.question, domain_id=None if domain_id == "all" else domain_id,
                top_k=requested_top_k, as_of_date=as_of_date,
                search_strategy=config.search_strategy,
                query_rewrite=config.query_rewrite,
                reranking=config.reranking,
            ))
            self._summarize_retrieval(run, retrieval, retry_count=0)
            evidence_decision = post_retrieval(retrieval)
            retry_step = self._step(run, "retry_control")
            if evidence_decision.action == "retry" and config.max_retries > 0:
                retry_step.status = "running"
                retry_step.started_at = utc_now()
                retry_started = perf_counter()
                retry_step.retry = True
                retry_step.retry_count = 1
                retry_step.input_summary = {"reason": evidence_decision.reason, "previous_top_k": requested_top_k}
                retry_top_k = min(50, requested_top_k + config.retry_top_k_increment)
                retried = self.service.retrieve(
                    run.question, domain_id=None if domain_id == "all" else domain_id,
                    top_k=retry_top_k, as_of_date=as_of_date,
                    search_strategy=config.search_strategy,
                    query_rewrite=True,
                    reranking=True,
                )
                retry_step.output_summary = {
                    "top_k": retry_top_k,
                    "evidence_count": len(retried.get("results", [])),
                    "previous_abstain": bool(retrieval.get("abstain")),
                    "retried_abstain": bool(retried.get("abstain")),
                    "quality_improved": bool(retrieval.get("abstain")) and not bool(retried.get("abstain")),
                }
                retry_step.duration_ms = round((perf_counter() - retry_started) * 1000, 3)
                retry_step.ended_at = utc_now()
                retry_step.status = "completed"
                run.retry_count = 1
                if not retried.get("abstain") and retried.get("results"):
                    retrieval = retried
                    requested_top_k = retry_top_k
                else:
                    retry_step.status = "warning"
                    retry_step.failure_reason = "retry_no_improvement"
                    run.response = retried
                    return self._finish_early(run, "retry_no_improvement", "abstain")
            else:
                retry_step.status = "skipped"
                retry_step.failure_reason = "retry_not_required" if evidence_decision.action != "retry" else "retry_limit_exceeded"
                if evidence_decision.action == "retry":
                    run.response = retrieval
                    return self._finish_early(run, "retry_limit_exceeded", "abstain")

            validation = self._record(run, "evidence_validation", lambda: retrieval.get("evidence_status", {}))
            val_step = self._step(run, "evidence_validation")
            val_step.output_summary = dict(validation)
            val_step.selected_evidence_ids = [str(row["document_id"]) for row in retrieval.get("results", [])]
            path = self._record(run, "reasoning_path", lambda: retrieval.get("legal_reasoning_path", {}))
            self._step(run, "reasoning_path").output_summary = {
                "enabled": bool(path.get("enabled")), "step_count": len(path.get("steps", []))
            }

            answer = self._record(run, "answer_generation", lambda: self.service.answer(
                run.question, domain_id=None if domain_id == "all" else domain_id,
                top_k=requested_top_k, as_of_date=as_of_date,
                search_strategy=config.search_strategy,
                query_rewrite=config.query_rewrite,
                reranking=config.reranking,
            ))
            gen_step = self._step(run, "answer_generation")
            gen_step.output_summary = {"generation_status": answer.get("generation_status"), "provider": answer.get("provider")}
            gen_step.selected_evidence_ids = list(map(str, answer.get("authoritative_evidence_ids", [])))

            checks = self._record(run, "citation_validation", lambda: {
                "citation": answer.get("citation_validation", {}),
                "grounding": answer.get("grounding_validation", {}),
            })
            check_step = self._step(run, "citation_validation")
            check_step.output_summary = {
                "citation_valid": checks["citation"].get("valid"),
                "grounding_valid": checks["grounding"].get("valid"),
            }
            quality_decision = post_generation(answer)
            quality = self._record(run, "quality_decision", lambda: answer.get("confidence", {}))
            quality_step = self._step(run, "quality_decision")
            quality_step.output_summary = dict(quality)
            quality_step.confidence = float(quality.get("score", 0.0))
            if quality_decision.action != "continue":
                quality_step.status = "warning"
                run.response = answer
                return self._finish_early(
                    run, quality_decision.reason or "quality_failure", quality_decision.action
                )

            run.response = answer
            run.outcome = "answered"
            run.final_quality = str(quality.get("level", "unknown"))
            final = self._step(run, "finalization")
            final.status = "completed"
            final.started_at = final.ended_at = utc_now()
            final.duration_ms = 0.0
            final.output_summary = {"outcome": run.outcome, "quality": run.final_quality}
            return self._complete(run)
        except Exception as exc:
            run.outcome = "failed"
            run.stop_reason = type(exc).__name__
            final = self._step(run, "finalization")
            final.status = "failed"
            final.failure_reason = run.stop_reason
            return self._complete(run)

    def _summarize_retrieval(self, run: AgentRun, response: dict[str, object], retry_count: int) -> None:
        step = self._step(run, "evidence_retrieval")
        results = list(response.get("results", []))
        step.search_strategy = run.config.search_strategy
        step.selected_evidence_ids = [str(row["document_id"]) for row in results]
        step.output_summary = {"evidence_count": len(results), "abstain": bool(response.get("abstain"))}
        step.confidence = float(results[0].get("score", 0.0)) if results else 0.0
        step.retry_count = retry_count

    def _finish_early(self, run: AgentRun, reason: str, action: str) -> AgentRun:
        run.stop_reason = reason
        run.outcome = "needs_clarification" if action == "clarify" else "abstained"
        run.response = {
            **run.response,
            "question": run.question,
            "abstain": True,
            "answer": run.response.get("answer", "신뢰할 수 있는 답변을 위해 추가 확인이 필요합니다."),
            "stop_reason": reason,
        }
        final = self._step(run, "finalization")
        final.status = "abstained"
        final.started_at = final.ended_at = utc_now()
        final.duration_ms = 0.0
        final.failure_reason = reason
        final.output_summary = {"outcome": run.outcome, "stop_reason": reason}
        for step in run.execution_trace:
            if step.status == "pending":
                step.status = "skipped"
        return self._complete(run)

    def _complete(self, run: AgentRun) -> AgentRun:
        run.status = "completed"
        run.completed_at = utc_now()
        self.store.save(run)
        return run
