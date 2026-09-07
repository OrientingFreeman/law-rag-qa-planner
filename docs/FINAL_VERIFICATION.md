# 검증 요약

## 최신 체크포인트: v4.27.6

현재 공개 코드의 최신 체크포인트는 v4.27.6이다. 아래 결과는 기능·데이터
품질 검증과 과거 Agent 실험을 구분해 기록한다. 특정 실행 환경의 수치를
일반적인 법률 판단 정확도나 생성형 모델 성능으로 해석하지 않는다.

| 항목 | 최신 확인 결과 |
| --- | --- |
| 전체 회귀 테스트 | `324 passed, 1 warning` |
| 실행 설정 | `LAW_RAG_LLM_PROVIDER=deterministic` |
| 실행 시간 | 174.25초 |
| 공식 평가 데이터 | 61개 사례의 schema·corpus 참조 검증 |
| Private OCR 품질 게이트 | 별도 private storage에서 `passed` |
| Private OCR 최종 상태 | 1,371 physical pages, 9,793 segments, review queue 0 |
| 적용된 private 보정 | text correction 2건, printed-page decision 124건 |

남은 테스트 경고는 Starlette TestClient와 `httpx`의 deprecation warning이며,
테스트 실패나 API 동작 오류가 아니다. private OCR의 원문, 페이지 snippet,
review queue, correction text와 source path는 공개 저장소에 포함하지 않는다.

v4.27.6의 구현 범위, 평가 버전 경계, 공개/비공개 경계와 미구현 범위는
[`PROJECT_CHECKPOINT_V4276.md`](../PROJECT_CHECKPOINT_V4276.md)를 참고한다.

## 역사적 기록: v4.17.0 Agent 검증

아래 내용은 v4.17.0 시점의 Agent Workflow 검증 기록이다. 최신 회귀 결과를
대체하지 않으며, 61개 사례 Baseline–Agent 비교의 조건과 기능 범위를 보존한다.

## v4.17.0 검증 결과

| 항목 | 결과 |
| --- | --- |
| 전체 테스트 | 246 passed |
| 평가 데이터 | 61개 문항 스키마·corpus 참조 검증 |
| Agent Workflow | 10단계 실행, 제한 재시도, 안전한 보류 |
| Trace | 상태·시간·신뢰도·전략·근거 ID·경고·중단 사유 기록 |
| 실험 비교 | 동일 데이터셋 Baseline–Agent 비교 및 사례 분류 |
| API | 실행·trace·실험·비교·실패 사례·검증 요약 조회 |
| 데모 | 실행 단계, 근거, 재시도, 보류 사유와 비교 지표 표시 |

전체 회귀 테스트 명령과 실제 결과:

```bash
LAW_RAG_LLM_PROVIDER=deterministic python -m pytest -q
# 246 passed, 1 warning
```

경고 1건은 FastAPI TestClient가 사용하는 Starlette의 `httpx` 호환성 폐기 예정 알림이며 테스트 실패나 현재 API 동작 오류가 아니다.

## 기능 확인

### Agent 실행과 trace

```bash
uvicorn law_rag.api.app:app --reload
```

- `POST /agent/runs`: Agent Workflow 실행
- `GET /agent/runs`: 최근 실행 목록
- `GET /agent/runs/{run_id}`: 최종 결과와 10단계 trace
- `GET /agent/runs/{run_id}/trace`: trace 전용 조회

### 실험과 실패 사례

- `POST /experiments`: 평가 실험 실행
- `GET /experiments`: 저장된 실험 목록
- `GET /experiments/{experiment_id}`: 실험 결과
- `POST /experiments/compare`: 두 실험 비교
- `GET /experiments/{experiment_id}/failures`: 실패 사례와 관련 run ID
- `GET /experiments/verified-summary`: 저장소에 검증된 비교 요약

브라우저에서 `/static/evaluation.html`을 열면 Agent 실행 trace와 Baseline–Agent 비교를 한 화면에서 확인할 수 있다.

## 데이터·실험 검증

```bash
python tools/validate_evaluation_dataset.py

LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode baseline --dataset evaluation/datasets/official_core_cases.json

LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode agent --dataset evaluation/datasets/official_core_cases.json
```

검증된 61문항 비교 결과는 `docs/EVALUATION_REPORT.md`와 `evaluation/baselines/v4.16.0_baseline_vs_agent_summary.json`에 기록했다. 원시 실험·trace·실패 로그는 재생성 가능한 실행 산출물이므로 기본적으로 Git에서 제외한다.

## 배포 전 확인

1. 로컬에서 전체 테스트와 데이터셋 검증을 실행한다.
2. 운영 환경의 corpus 및 LLM provider 설정을 확인한다.
3. 비밀키는 환경 변수로 주입하고 ZIP이나 저장소에 포함하지 않는다.
4. `/health`, 기존 `/answer`, 신규 `/agent/runs`를 순서대로 smoke test한다.
5. 장시간 평가 실험은 웹 요청 처리 프로세스와 분리하는 것을 권장한다.

## 알려진 한계

- 실험 API는 안전한 최소 구현이며 대규모 작업 큐나 분산 실행기가 아니다.
- 실행·실험 저장소는 단일 프로세스와 소규모 데모를 우선한다.
- 보류 정책은 안전성을 높이지만 답변 가능한 문항의 불필요한 보류가 증가할 수 있다.
- 검증 실행의 재시도 12건에서는 실제 품질 개선이 관측되지 않았다.
- 61개 평가의 통과율을 생성형 답변 정확도 100% 또는 실서비스 성능으로 해석하면 안 된다.
