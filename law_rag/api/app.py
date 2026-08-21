from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from law_rag.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    ExperimentCompareRequest,
    ExperimentResponse,
    ExperimentRunRequest,
    AnswerResponse,
    DomainResponse,
    EvaluationRunRequest,
    EvaluationReviewRequest,
    EvaluationRunResponse,
    HealthResponse,
    LawResponse,
    QueryRequest,
    QueryResponse,
    RetrieveResponse,
)
from law_rag.evaluation.runner import EvaluationRunner, load_dataset, write_report
from law_rag.evaluation.datasets import dataset_snapshot
from law_rag.evaluation.reviews import JsonReviewStore, ReviewRecord
from law_rag.evaluation.hard_negatives import JsonlCandidateStore
from law_rag.evaluation.comparison import compare_experiments
from law_rag.evaluation.experiments import ExperimentConfig, ExperimentRunner, ExperimentStore
from law_rag.service import LawRagService
from law_rag.workflow import AgentWorkflowRunner, InMemoryTraceStore, WorkflowConfig

from law_rag import __version__

APP_VERSION = __version__
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(
    *,
    data_path: str | Path | None = None,
    domains_path: str | Path | None = None,
    precedent_data_path: str | Path | None = None,
    evaluation_dataset_path: str | Path | None = None,
    evaluation_report_path: str | Path | None = None,
) -> FastAPI:
    resolved_data_path = Path(data_path or os.getenv("LAW_RAG_DATA_PATH", "data/legal_corpus.json"))
    resolved_domains_path = Path(domains_path or os.getenv("LAW_RAG_DOMAINS_PATH", "domains"))
    resolved_precedent_path = Path(
        precedent_data_path or os.getenv("LAW_RAG_PRECEDENT_DATA_PATH", "data/precedent_poc.json")
    )
    resolved_dataset_path = Path(
        evaluation_dataset_path
        or os.getenv("LAW_RAG_EVALUATION_DATASET", "evaluation/datasets/official_core_cases.json")
    )
    resolved_report_path = Path(
        evaluation_report_path
        or os.getenv("LAW_RAG_EVALUATION_REPORT", "evaluation/reports/latest.json")
    )
    resolved_experiment_dir = Path(os.getenv("LAW_RAG_EXPERIMENT_DIR", "evaluation/experiments"))
    resolved_review_path = Path(os.getenv(
        "LAW_RAG_REVIEW_STORE", "evaluation/reviews/review_records.jsonl"
    ))
    resolved_hard_negative_path = Path(os.getenv(
        "LAW_RAG_HARD_NEGATIVE_CANDIDATES",
        "evaluation/training/hard_negative_candidates.jsonl",
    ))
    resolved_verified_summary = Path(os.getenv(
        "LAW_RAG_VERIFIED_EXPERIMENT_SUMMARY",
        "evaluation/baselines/v4.16.0_baseline_vs_agent_summary.json",
    ))
    public_demo = os.getenv("LAW_RAG_PUBLIC_DEMO", "false").strip().lower() in {"1", "true", "yes", "on"}
    evaluation_run_enabled = os.getenv(
        "LAW_RAG_ENABLE_EVALUATION_RUN",
        "false" if public_demo else "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    demo_max_requests = max(1, int(os.getenv("LAW_RAG_DEMO_MAX_REQUESTS", "20")))
    demo_window_seconds = max(60, int(os.getenv("LAW_RAG_DEMO_WINDOW_SECONDS", "3600")))
    request_history: dict[str, deque[float]] = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.law_rag_service = LawRagService(
            data_path=resolved_data_path,
            domains_path=resolved_domains_path,
            precedent_data_path=resolved_precedent_path,
        )
        app.state.evaluation_dataset_path = resolved_dataset_path
        app.state.evaluation_report_path = resolved_report_path
        app.state.agent_trace_store = InMemoryTraceStore()
        app.state.agent_workflow = AgentWorkflowRunner(
            app.state.law_rag_service, app.state.agent_trace_store
        )
        app.state.experiment_store = ExperimentStore(resolved_experiment_dir)
        app.state.review_store = JsonReviewStore(resolved_review_path)
        app.state.hard_negative_store = JsonlCandidateStore(resolved_hard_negative_path)
        app.state.verified_experiment_summary = resolved_verified_summary
        yield

    app = FastAPI(
        title="Law RAG QA Planner API",
        description="도메인 확장형 한국 법령 검색 및 근거 기반 QA API",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def public_demo_rate_limit(request: Request, call_next):
        limited_paths = {"/answer", "/query", "/retrieve", "/agent/runs"}
        if public_demo and request.method == "POST" and request.url.path in limited_paths:
            client_key = request.client.host if request.client else "unknown"
            now = time.monotonic()
            history = request_history[client_key]
            while history and now - history[0] >= demo_window_seconds:
                history.popleft()
            if len(history) >= demo_max_requests:
                retry_after = max(1, int(demo_window_seconds - (now - history[0])))
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "detail": {
                            "code": "demo_rate_limit_exceeded",
                            "message": "공개 데모의 시간당 질의 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                            "retry_after_seconds": retry_after,
                        }
                    },
                )
            history.append(now)
        return await call_next(request)

    def get_service(request: Request) -> LawRagService:
        return request.app.state.law_rag_service

    def validate_domain(service: LawRagService, domain_id: str) -> None:
        if domain_id == "all":
            return
        if service.registry.get(domain_id) is None:
            available = [domain["domain_id"] for domain in service.list_domains()]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "domain_not_found",
                    "message": f"알 수 없는 도메인입니다: {domain_id}",
                    "available_domains": available,
                },
            )

    def enforce_review_gate(request: Request, cases: list[object]) -> None:
        snapshot = checked_dataset_snapshot(
            request.app.state.evaluation_dataset_path,
            case_count=len(load_dataset(request.app.state.evaluation_dataset_path)),
        )
        default_status = "approved" if snapshot.get("status") in {"released", "unmanaged"} else "review_required"
        latest = request.app.state.review_store.latest(target_type="evaluation_case")
        blocked = [
            str(case.case_id) for case in cases
            if latest.get(str(case.case_id), {}).get("review_status", default_status) != "approved"
        ]
        if blocked:
            raise HTTPException(status_code=409, detail={
                "code": "evaluation_review_gate_failed",
                "message": "승인되지 않은 평가 사례가 포함되어 있습니다.",
                "case_ids": blocked,
            })

    def checked_dataset_snapshot(dataset_path: Path, *, case_count: int) -> dict[str, object]:
        try:
            return dataset_snapshot(dataset_path, case_count=case_count)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            raise HTTPException(status_code=409, detail={
                "code": "dataset_manifest_invalid",
                "message": "평가 데이터셋과 manifest가 일치하지 않습니다.",
                "reason": str(exc),
            }) from exc

    @app.get("/", include_in_schema=False)
    def web_ui() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/internal/evaluation", include_in_schema=False)
    def internal_evaluation_ui() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "evaluation.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/internal/training-review", include_in_schema=False)
    def internal_training_review_ui() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "training-review.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/demo-config", include_in_schema=False)
    def demo_config() -> dict[str, object]:
        return {
            "public_demo": public_demo,
            "evaluation_run_enabled": evaluation_run_enabled,
            "max_requests": demo_max_requests if public_demo else None,
            "window_seconds": demo_window_seconds if public_demo else None,
        }

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health(service: LawRagService = Depends(get_service)) -> dict[str, object]:
        return {
            "status": "ok",
            "service": "law-rag-qa-planner",
            "version": APP_VERSION,
            "provision_count": len(service.provisions),
            "domain_count": len(service.list_domains()),
        }

    @app.get("/domains", response_model=list[DomainResponse], tags=["metadata"])
    def domains(service: LawRagService = Depends(get_service)) -> list[dict[str, object]]:
        return service.list_domains()

    @app.get("/laws", response_model=list[LawResponse], tags=["metadata"])
    def laws(domain: str = "all", service: LawRagService = Depends(get_service)) -> list[dict[str, object]]:
        validate_domain(service, domain)
        return service.list_laws(domain_id=domain)

    @app.post("/retrieve", response_model=RetrieveResponse, tags=["retrieval"])
    def retrieve(payload: QueryRequest, service: LawRagService = Depends(get_service)) -> dict[str, object]:
        validate_domain(service, payload.domain)
        return service.retrieve(payload.question, domain_id=payload.domain, top_k=payload.top_k, as_of_date=payload.as_of_date)

    @app.post("/answer", response_model=AnswerResponse, tags=["qa"])
    def answer(payload: QueryRequest, service: LawRagService = Depends(get_service)) -> dict[str, object]:
        validate_domain(service, payload.domain)
        return service.answer(payload.question, domain_id=payload.domain, top_k=payload.top_k, as_of_date=payload.as_of_date)

    @app.post("/query", response_model=QueryResponse, tags=["qa"])
    def query(payload: QueryRequest, service: LawRagService = Depends(get_service)) -> dict[str, object]:
        validate_domain(service, payload.domain)
        return service.query(payload.question, domain_id=payload.domain, top_k=payload.top_k, as_of_date=payload.as_of_date)

    @app.post("/agent/runs", response_model=AgentRunResponse, tags=["agent"])
    def run_agent(payload: AgentRunRequest, request: Request,
                  service: LawRagService = Depends(get_service)) -> dict[str, object]:
        validate_domain(service, payload.domain)
        runner: AgentWorkflowRunner = request.app.state.agent_workflow
        run = runner.run(
            payload.question,
            domain_id=payload.domain,
            top_k=payload.top_k,
            as_of_date=payload.as_of_date,
            config=WorkflowConfig(
                search_strategy=payload.search_strategy,
                query_rewrite=payload.query_rewrite,
                reranking=payload.reranking,
                max_retries=payload.max_retries,
                retry_top_k_increment=payload.retry_top_k_increment,
                abstention_policy=payload.abstention_policy,
            ),
        )
        return run.to_dict()

    @app.get("/agent/runs", response_model=list[AgentRunResponse], tags=["agent"])
    def list_agent_runs(request: Request, limit: int = 20) -> list[dict[str, object]]:
        limit = max(1, min(limit, 100))
        store: InMemoryTraceStore = request.app.state.agent_trace_store
        return [run.to_dict() for run in store.list(limit)]

    @app.get("/agent/runs/{run_id}", response_model=AgentRunResponse, tags=["agent"])
    def get_agent_run(run_id: str, request: Request) -> dict[str, object]:
        store: InMemoryTraceStore = request.app.state.agent_trace_store
        run = store.get(run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "agent_run_not_found", "message": "Agent 실행 기록을 찾을 수 없습니다."},
            )
        return run.to_dict()

    @app.post("/experiments/run", response_model=ExperimentResponse, tags=["experiments"])
    def run_experiment(payload: ExperimentRunRequest, request: Request,
                       service: LawRagService = Depends(get_service)) -> dict[str, object]:
        if not evaluation_run_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "experiment_run_disabled", "message": "공개 데모에서는 실험 실행이 비활성화되어 있습니다."},
            )
        config = ExperimentConfig(
            mode=payload.mode,
            dataset_path=str(request.app.state.evaluation_dataset_path),
            experiment_kind=payload.experiment_kind,
            seed=payload.seed,
            baseline_experiment_id=payload.baseline_experiment_id,
            treatment_name=payload.treatment_name,
            retriever_version=payload.retriever_version,
            embedding_model=payload.embedding_model,
            reranker_model=payload.reranker_model,
            prompt_version=payload.prompt_version,
            search_strategy=payload.search_strategy,
            query_rewrite=payload.query_rewrite,
            reranking=payload.reranking,
            max_retries=payload.max_retries,
            retry_top_k_increment=payload.retry_top_k_increment,
            abstention_policy=payload.abstention_policy,
        )
        selected_cases = load_dataset(config.dataset_path)
        if payload.case_ids:
            selected = set(payload.case_ids)
            selected_cases = [case for case in selected_cases if case.case_id in selected]
        if payload.limit is not None:
            selected_cases = selected_cases[:payload.limit]
        enforce_review_gate(request, selected_cases)
        report = ExperimentRunner(service).run(config, case_ids=payload.case_ids, limit=payload.limit)
        request.app.state.experiment_store.save(report)
        return report

    @app.get("/experiments", tags=["experiments"])
    def list_experiments(request: Request) -> list[dict[str, object]]:
        return request.app.state.experiment_store.list()

    @app.get("/experiments/verified-summary", tags=["experiments"])
    def verified_experiment_summary(request: Request) -> dict[str, object]:
        path: Path = request.app.state.verified_experiment_summary
        if not path.exists():
            raise HTTPException(status_code=404, detail={
                "code": "verified_summary_not_found",
                "message": "검증된 실험 요약을 찾을 수 없습니다.",
            })
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/experiments/ablations", tags=["experiments"])
    def list_retrieval_ablations(request: Request) -> list[dict[str, object]]:
        return request.app.state.experiment_store.list_ablation_reports()

    @app.get("/experiments/{experiment_id}", response_model=ExperimentResponse, tags=["experiments"])
    def get_experiment(experiment_id: str, request: Request) -> dict[str, object]:
        report = request.app.state.experiment_store.get(experiment_id)
        if report is None:
            raise HTTPException(status_code=404, detail={"code": "experiment_not_found", "message": "실험 결과를 찾을 수 없습니다."})
        return report

    @app.post("/experiments/compare", tags=["experiments"])
    def compare_saved_experiments(payload: ExperimentCompareRequest, request: Request) -> dict[str, object]:
        store: ExperimentStore = request.app.state.experiment_store
        baseline = store.get(payload.baseline_experiment_id)
        candidate = store.get(payload.candidate_experiment_id)
        if baseline is None or candidate is None:
            raise HTTPException(status_code=404, detail={"code": "experiment_not_found", "message": "비교할 실험 결과를 찾을 수 없습니다."})
        try:
            return compare_experiments(baseline, candidate)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "incompatible_experiments", "message": str(exc)}) from exc

    @app.get("/experiments/{experiment_id}/failures", tags=["experiments"])
    def experiment_failures(experiment_id: str, request: Request) -> list[dict[str, object]]:
        report = request.app.state.experiment_store.get(experiment_id)
        if report is None:
            raise HTTPException(status_code=404, detail={"code": "experiment_not_found", "message": "실험 결과를 찾을 수 없습니다."})
        return [row for row in report["cases"] if not row["passed"]]

    @app.get("/evaluation/reviews/queue", tags=["evaluation"])
    def evaluation_review_queue(request: Request, include_approved: bool = False) -> dict[str, object]:
        dataset_path: Path = request.app.state.evaluation_dataset_path
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
        rows = raw["cases"] if isinstance(raw, dict) else raw
        snapshot = checked_dataset_snapshot(dataset_path, case_count=len(rows))
        latest = request.app.state.review_store.latest(target_type="evaluation_case")
        default_status = "approved" if snapshot.get("status") == "released" else "review_required"
        queue: list[dict[str, object]] = []
        for row in rows:
            case_id = str(row["case_id"])
            review = latest.get(case_id)
            status_value = review["review_status"] if review else str(row.get("review_status") or default_status)
            if include_approved or status_value in {"draft", "review_required", "rejected"}:
                queue.append({
                    "case_id": case_id,
                    "question": row["question"],
                    "category": row.get("category"),
                    "difficulty": row.get("difficulty"),
                    "review_status": status_value,
                    "latest_review": review,
                })
        return {"dataset": snapshot, "queue_count": len(queue), "cases": queue}

    @app.post("/evaluation/reviews", tags=["evaluation"])
    def save_evaluation_review(payload: EvaluationReviewRequest, request: Request) -> dict[str, str]:
        if not evaluation_run_enabled:
            raise HTTPException(status_code=403, detail={
                "code": "review_write_disabled", "message": "현재 서버에서는 검수 기록 저장이 비활성화되어 있습니다."
            })
        dataset_path: Path = request.app.state.evaluation_dataset_path
        cases = load_dataset(dataset_path)
        if payload.target_type == "evaluation_case":
            if payload.target_id not in {case.case_id for case in cases}:
                raise HTTPException(status_code=404, detail={
                    "code": "review_target_not_found", "message": "검수할 평가 사례를 찾을 수 없습니다."
                })
            snapshot = checked_dataset_snapshot(dataset_path, case_count=len(cases))
        else:
            candidate = request.app.state.hard_negative_store.get(payload.target_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail={
                    "code": "review_target_not_found", "message": "검수할 hard-negative 후보를 찾을 수 없습니다."
                })
            source = candidate.get("source", {})
            snapshot = {
                "dataset_id": "hard_negative_candidates",
                "dataset_version": str(candidate.get("candidate_pool_version", "unversioned")),
                "ground_truth_version": str(source.get("ground_truth_version", "unversioned")),
            }
        try:
            record = ReviewRecord.create(
                target_type=payload.target_type,
                target_id=payload.target_id,
                dataset_id=str(snapshot["dataset_id"]),
                dataset_version=str(snapshot["dataset_version"]),
                ground_truth_version=str(snapshot["ground_truth_version"]),
                decision=payload.decision,
                reviewer_id=payload.reviewer_id,
                review_comment=payload.review_comment,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_review", "message": str(exc)}) from exc
        request.app.state.review_store.append(record)
        return record.to_dict()

    @app.get("/training/hard-negatives/queue", tags=["training"])
    def hard_negative_review_queue(
        request: Request, include_processed: bool = False,
        include_approved: bool = False, limit: int = 50,
        domain: str | None = None, candidate_pool_version: str | None = None,
        one_per_case: bool = True,
    ) -> dict[str, object]:
        limit = max(1, min(limit, 200))
        all_candidates = request.app.state.hard_negative_store.list()
        domain_candidates = [
            row for row in all_candidates
            if domain is None or str(row.get("domain", "all")) == domain
        ]
        available_versions = sorted({
            str(row.get("candidate_pool_version", "unversioned"))
            for row in domain_candidates
        })
        candidates = [
            row for row in domain_candidates
            if candidate_pool_version is None
            or str(row.get("candidate_pool_version", "unversioned")) == candidate_pool_version
        ]
        latest = request.app.state.review_store.latest(target_type="training_candidate")
        queue: list[dict[str, object]] = []
        for candidate in candidates:
            candidate_id = str(candidate["candidate_id"])
            review = latest.get(candidate_id)
            status_value = review["review_status"] if review else "review_required"
            processed = review is not None
            # include_approved remains as a backwards-compatible alias for old clients.
            if (
                not processed or include_processed
                or (include_approved and status_value == "approved")
            ):
                queue.append({
                    **candidate, "review_status": status_value,
                    "review_processed": processed, "latest_review": review,
                })
        ungrouped_count = len(queue)
        hidden_by_case: dict[str, int] = {}
        if one_per_case:
            grouped: list[dict[str, object]] = []
            seen: set[tuple[str, str]] = set()
            for row in queue:
                key = (
                    str(row.get("source", {}).get("case_id", "")),
                    str(row.get("source", {}).get("method", "")),
                )
                label = ":".join(key)
                if key in seen:
                    hidden_by_case[label] = hidden_by_case.get(label, 0) + 1
                    continue
                seen.add(key)
                grouped.append(row)
            queue = grouped
            for row in queue:
                key = ":".join((
                    str(row.get("source", {}).get("case_id", "")),
                    str(row.get("source", {}).get("method", "")),
                ))
                row["additional_candidate_count"] = hidden_by_case.get(key, 0)
        return {
            "candidate_pool": {
                "dataset_id": "hard_negative_candidates",
                "versions": available_versions,
                "selected_version": candidate_pool_version,
                "candidate_count": len(candidates),
                "total_candidate_count": len(all_candidates),
                "domain": domain,
                "one_per_case": one_per_case,
            },
            "queue_count": len(queue),
            "ungrouped_queue_count": ungrouped_count,
            "hidden_additional_count": ungrouped_count - len(queue),
            "returned_count": min(len(queue), limit),
            "processed_count": sum(
                str(candidate["candidate_id"]) in latest for candidate in candidates
            ),
            "pending_count": sum(
                str(candidate["candidate_id"]) not in latest for candidate in candidates
            ),
            "candidates": queue[:limit],
        }

    @app.get("/evaluation/latest", response_model=EvaluationRunResponse, tags=["evaluation"])
    def latest_evaluation(request: Request) -> dict[str, object]:
        path: Path = request.app.state.evaluation_report_path
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "evaluation_report_not_found", "message": "저장된 평가 리포트가 없습니다."},
            )
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/evaluation/run", response_model=EvaluationRunResponse, tags=["evaluation"])
    def run_evaluation(
        payload: EvaluationRunRequest,
        request: Request,
        service: LawRagService = Depends(get_service),
    ) -> dict[str, object]:
        if not evaluation_run_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "evaluation_run_disabled",
                    "message": "공개 데모에서는 평가 실행이 비활성화되어 있습니다. 저장된 평가 리포트만 조회할 수 있습니다.",
                },
            )
        dataset_path: Path = request.app.state.evaluation_dataset_path
        report_path: Path = request.app.state.evaluation_report_path
        if not dataset_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "evaluation_dataset_not_found", "message": "평가 데이터셋을 찾을 수 없습니다."},
            )
        cases = load_dataset(dataset_path)
        if payload.case_ids:
            selected = set(payload.case_ids)
            cases = [case for case in cases if case.case_id in selected]
        if payload.limit is not None:
            cases = cases[: payload.limit]
        if not cases:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "evaluation_cases_empty", "message": "실행할 평가 사례가 없습니다."},
            )
        enforce_review_gate(request, cases)
        report = EvaluationRunner(service).run(cases)
        report["version"] = APP_VERSION
        write_report(report, report_path)
        return report

    return app


app = create_app()
