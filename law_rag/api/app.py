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
from law_rag.service import LawRagService

from law_rag import __version__

APP_VERSION = __version__
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(
    *,
    data_path: str | Path | None = None,
    domains_path: str | Path | None = None,
    evaluation_dataset_path: str | Path | None = None,
    evaluation_report_path: str | Path | None = None,
) -> FastAPI:
    resolved_data_path = Path(data_path or os.getenv("LAW_RAG_DATA_PATH", "data/legal_corpus.json"))
    resolved_domains_path = Path(domains_path or os.getenv("LAW_RAG_DOMAINS_PATH", "domains"))
    resolved_dataset_path = Path(
        evaluation_dataset_path
        or os.getenv("LAW_RAG_EVALUATION_DATASET", "evaluation/datasets/core_cases.json")
    )
    resolved_report_path = Path(
        evaluation_report_path
        or os.getenv("LAW_RAG_EVALUATION_REPORT", "evaluation/reports/latest.json")
    )
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
        )
        app.state.evaluation_dataset_path = resolved_dataset_path
        app.state.evaluation_report_path = resolved_report_path
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
        limited_paths = {"/answer", "/query", "/retrieve"}
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
