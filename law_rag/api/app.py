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
    EvaluationRunResponse,
    HealthResponse,
    LawResponse,
    QueryRequest,
    QueryResponse,
    RetrieveResponse,
)
from law_rag.evaluation.runner import EvaluationRunner, load_dataset, write_report
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
        or os.getenv("LAW_RAG_EVALUATION_DATASET", "evaluation/datasets/core_cases.json")
    )
    resolved_report_path = Path(
        evaluation_report_path
        or os.getenv("LAW_RAG_EVALUATION_REPORT", "evaluation/reports/latest.json")
    )
    resolved_experiment_dir = Path(os.getenv("LAW_RAG_EXPERIMENT_DIR", "evaluation/experiments"))
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
            dataset_version=payload.dataset_version,
            search_strategy=payload.search_strategy,
            query_rewrite=payload.query_rewrite,
            reranking=payload.reranking,
            max_retries=payload.max_retries,
            retry_top_k_increment=payload.retry_top_k_increment,
            abstention_policy=payload.abstention_policy,
        )
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
        report = EvaluationRunner(service).run(cases)
        report["version"] = APP_VERSION
        write_report(report, report_path)
        return report

    return app


app = create_app()
