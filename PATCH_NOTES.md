## v4.25.1 - Completed Review Queue UX

- 승인뿐 아니라 수정 요청·거절도 한 번 처리된 후보로 판정해 기본 검수 큐에서 제외합니다.
- `처리된 후보도 표시`를 선택하면 모든 처리 결과를 다시 조회할 수 있습니다.
- 처리된 후보는 textarea와 결정 버튼 대신 검수 결과·의견·검수자·처리시각을 읽기 전용 텍스트로 표시합니다.
- 수정 요청은 경고색, 승인은 성공색, 거절은 오류색으로 구분합니다.
- 검수 저장 요청이 시작되면 결정 버튼을 잠가 빠른 중복 클릭으로 동일 작업이 여러 번 기록되는 것을 방지합니다.
- 기존 `include_approved` API query는 승인 결과만 표시하는 하위 호환 동작으로 유지합니다.
- 기존 append-only 검수 기록과 승인 dataset export 정책은 변경하지 않습니다.

## v4.25.0 - Civil ML Experiment Readiness Gate

- 민법 approved split, 민법 gold-bearing 평가 문항, 선택 ML 의존성, fine-tuned checkpoint를 독립 gate로 검사합니다.
- pretrained embedding, pretrained + reranker, fine-tuning, fine-tuned embedding, fine-tuned + reranker의 실행 가능 상태를 하나의 matrix로 기록합니다.
- 준비된 미실행 단계는 `not_run`, 조건이 없는 단계는 `unavailable`로 구분합니다.
- checkpoint가 없어도 pretrained baseline과 fine-tuning 준비 상태는 별도로 판정합니다.
- gate는 모델을 다운로드·학습·평가하지 않으며 performance metric을 생성하지 않습니다.
- 결과를 기존 JSON Experiment Store에 저장하여 이후 실제 ML 실행 조건의 근거로 사용합니다.

## v4.24.0 - Civil Approved Dataset Export & Split Preparation

- 기존 generic export를 유지하면서 `civil_transactions` domain과 `civil-*` candidate pool version을 함께 지정할 수 있습니다.
- 승인된 후보 중 선택 범위에 일치하는 레코드만 export하고 domain, category, candidate pool version을 보존합니다.
- export manifest에 선택 조건, 승인 건수, 원본 dataset version과 corpus checksum을 기록합니다.
- train/validation 준비 단계에서 manifest와 각 레코드의 domain·candidate pool version 일치를 검증합니다.
- 동일 dataset case/query를 split group으로 묶어 누수를 차단하고 각 split의 group 목록과 hash를 기록합니다.
- 개인정보보호법 등 기존 승인 데이터와 회귀 baseline은 변경하거나 삭제하지 않습니다.
- 첨부 패키지에는 로컬 수동 검수 이력이 없으므로 실제 민법 dataset은 승인 기록이 있는 사용자 환경에서만 생성됩니다.

## v4.23.1 - Grouped Hard-negative Review Queue

- 같은 평가 사례와 retrieval method에서 파생된 여러 hard negative를 기본적으로 사례당 한 장으로 묶어 표시합니다.
- 숨겨진 추가 후보 수를 표시하고 `같은 사례의 추가 후보도 표시`를 선택하면 모든 후보를 독립적으로 검수할 수 있습니다.
- candidate pool version 필터를 추가해 기존 후보와 신규 민법 배치를 구분합니다.
- 기존 append-only 후보·검수 기록은 삭제하거나 변경하지 않습니다.

## v4.23.0 - Civil-law ML Review Readiness

- 기존 개인정보보호법 corpus·평가·회귀 baseline을 변경하지 않고 신규 ML 수동 검수의 기본 도메인을 민법으로 분리합니다.
- 도메인별 corpus 범위, 평가 문항, gold 근거 해소 여부, benchmark 실패와 hard-negative 후보를 감사하는 CLI를 추가합니다.
- 실제 Hybrid 결과에서 사례당 후보 하나를 우선하는 결정론적 10~20건 검수 배치를 생성할 수 있습니다.
- hard-negative 생성 CLI에 도메인, 최대 건수, 사례당 하나 필터를 추가합니다.
- 전용 검수 페이지와 API에서 민법·개인정보·전자금융·노동 후보를 도메인별로 조회합니다.
- 자동 발견 후보는 계속 `review_required`이며, 수동 승인 전 자동 학습을 허용하지 않습니다.
- synthetic 민법 사례나 신규 정답 데이터는 이번 패치에서 추가하지 않습니다.

## v4.22.0 - Retrieval Ablation Runner

- BM25부터 fine-tuned embedding + reranker까지 일곱 검색 조합을 하나의 재현 가능한 실행 계획으로 관리합니다.
- 기본 명령은 모델을 실행하지 않는 plan-only이며, `--execute`로 명시한 사용 가능한 조합만 실제 benchmark를 수행합니다.
- 조합별 `not_run`, `unavailable`, `completed`, `failed` 상태를 기록하고 미실행 조합에는 metric을 생성하지 않습니다.
- 동일 dataset·corpus checksum, 사례 선택, Top-K 조건을 검사한 뒤 baseline/treatment의 metric·latency delta와 품질 회귀를 판정합니다.
- 전체 지표와 법률 분야별 지표를 분리하고 사례 개선·악화 수를 기록합니다.
- 결과를 기존 Experiment Store에 저장하고 Evaluation UI의 Retrieval Ablation 영역에서 조회합니다.
- runner는 특정 법률 도메인에 종속되지 않으며 민법 학습·검수 데이터 보강은 다음 별도 패치로 유지합니다.

## v4.21.0 - Optional Cross-Encoder Reranker Infrastructure

- core retriever와 독립된 `ProvisionReranker` interface와 lazy-loaded Sentence Transformers `CrossEncoder` adapter를 추가합니다.
- retriever Top-N 후보만 rerank하고 최종 Top-K를 반환하며, 동점은 원래 retrieval 순서를 보존합니다.
- benchmark에서 semantic-lite, hybrid, pretrained embedding, fine-tuned embedding의 reranker 조합을 명시적으로 선택할 수 있습니다.
- retrieval latency와 reranking latency를 문항별·평균으로 분리하고 reranker score와 original rank를 기록합니다.
- reranker를 사용하지 않으면 기존 ranking이 변하지 않으며 ML 모델을 다운로드하지 않습니다.
- injected fake CrossEncoder로 CI를 검증하고, 실제 실행하지 않은 모델 조합의 성능 수치는 기록하지 않습니다.

## v4.20.0 - Reproducible Embedding Training Pipeline

- 승인된 hard-negative dataset의 manifest hash, record count, review 상태와 positive/negative 충돌을 학습 전에 검증합니다.
- 동일 evaluation case 또는 query가 train과 validation에 동시에 들어가지 않도록 group 단위 deterministic split을 생성합니다.
- query, positive, hard negative triplet과 각 split의 SHA-256을 기록합니다.
- Sentence Transformers의 TripletLoss 기반 fine-tuning entry point를 추가하되 기본 동작은 plan-only로 유지합니다.
- 실제 학습은 `--execute`를 명시해야 하며, checkpoint와 설정·seed·dataset version은 기존 JSON Experiment Store 형식으로 기록합니다.
- 학습을 실행하지 않은 상태에서는 성능 metric을 생성하거나 주장하지 않습니다.

## v4.19.1 - Hard-negative 검수 전용 페이지

- Agent 실행·평가 콘솔과 학습 후보 검수 화면을 분리했습니다.
- `/internal/training-review`에서 Positive와 Hard negative의 의미를 확인하며 후보를 검수할 수 있습니다.
- 기존 후보 파일, append-only 검수 이력, API는 그대로 유지하므로 데이터 마이그레이션이 필요 없습니다.
- 평가 콘솔에서는 학습 후보 전용 DOM과 이벤트를 제거해 두 화면의 책임을 명확히 했습니다.

## v4.19.0 - Hard-negative Candidate와 Human Review

- Retrieval Benchmark의 `wrong_top1`, `retrieval_miss`, `over_retrieval`에서 후보를 생성합니다.
- 실제 corpus의 조문·항·호 본문을 positive와 hard-negative에 포함합니다.
- 내용 기반 candidate ID로 재실행 중복을 차단하고 positive/negative 충돌을 거부합니다.
- 기존 append-only Human Review에 `training_candidate` 전용 큐를 연결합니다.
- 승인된 후보만 versioned JSONL training dataset과 checksum manifest로 export합니다.
- 공개 데모의 검수 쓰기 차단 정책을 그대로 적용합니다.
- embedding fine-tuning과 자동 재학습은 다음 독립 패치로 유지합니다.

## v4.18.0 - 재현 가능한 Retrieval Benchmark

- 공식 61문항에서 gold-bearing non-abstention retrieval 문항 45개를 자동 분리합니다.
- BM25, 기존 문자 n-gram `semantic_lite`, production hybrid를 동일 조건에서 비교합니다.
- 선택 의존성으로 실제 Sentence Transformers pretrained embedding을 실행할 수 있습니다.
- Top-1 Accuracy, Hit@K, Recall@K, MRR, binary relevance nDCG@K와 latency를 저장합니다.
- dataset/corpus checksum, seed, code/model version과 문항별 순위를 JSON으로 기록합니다.
- CI에서 Hit@K와 MRR 기준선 하락을 감지합니다.
- hard-negative dataset과 embedding fine-tuning은 다음 독립 패치로 유지합니다.

## v4.17.2 - 콘솔에서 Baseline·Agent 실험 실행

- 저장된 실험 영역에서 61개 전체 데이터의 Baseline 또는 Agent 실험을 직접 실행할 수 있습니다.
- 실행 중 중복 요청을 차단하고, 완료된 실험을 저장한 뒤 해당 선택 목록에 자동 반영합니다.
- 공개 환경에서 평가 실행이 비활성화되면 실행 버튼도 함께 숨깁니다.

## v4.17.1 - 홈에서 Agent 평가 콘솔로 이동

- 홈 상단 탐색 메뉴와 주요 실행 버튼에 Agent 실행·평가 콘솔 진입 경로를 추가했습니다.
- 좁은 화면에서도 기존 CTA와 함께 세로로 배치되도록 기존 반응형 규칙을 재사용했습니다.

## v4.17.0 - Agent Trace 데모와 최종 문서화

- 기존 내부 평가 콘솔에 10단계 Agent 실행 Trace를 표시합니다.
- 단계별 성공·경고·보류·실패, 검색 전략, 선택 근거, 재시도, confidence와 중단 사유를 확인할 수 있습니다.
- 검증된 61개 Baseline/Agent 비교 결과와 안전성·응답시간 트레이드오프를 표시합니다.
- 저장된 두 실험의 개선·악화·동일 실패 사례와 Agent run ID를 비교합니다.
- 검증 요약 조회 API를 추가하고 공개 환경에서는 기존 평가 실행 제한을 유지합니다.
- README, Agent Workflow, 실험 비교, 평가 보고서와 최종 검증 문서를 실제 측정 결과에 맞게 갱신합니다.
- 외부 공개 문구를 특정 조직이나 사용 목적에 종속되지 않는 범용 기술 데모 설명으로 정리했습니다.

## v4.16.0 - Safety Evaluation과 재현 가능한 실험 비교

- 안전한 보류·추가 사실 요청·정상 답변을 검증하는 경계 사례 12개를 추가해 공식 평가 데이터를 61개로 확장했습니다.
- lexical, semantic, hybrid 검색 전략과 query rewrite·ontology reranking 설정을 실제 실행 옵션으로 분리했습니다.
- Baseline과 Agent Workflow를 같은 사례·데이터 버전·검색 설정으로 실행하는 실험 러너를 추가했습니다.
- 검색, 답변·근거, Agent 안전성 지표를 분리하고 평균 응답시간·재시도·실패 사유를 함께 저장합니다.
- 두 실험의 개선·악화·동일 통과·동일 실패 사례 및 실패 유형 증감을 비교합니다.
- Agent 실패 사례에 `run_id`와 전체 `execution_trace`를 연결합니다.
- 실험 실행·목록·상세·비교·실패 사례 조회 API와 CLI를 제공합니다.
- 실험 원문은 Git에서 제외하며 실제 측정 결과는 실행 환경·설정과 함께 JSON으로 재현합니다.

## v4.15.0 - Agent Core와 실행 추적

- 기존 검색·추론·생성 기능을 10단계의 명시적인 Agent Workflow로 오케스트레이션합니다.
- 각 실행에 `run_id`를 부여하고 단계 상태, 소요시간, 검색 전략, 선택 근거, 경고와 중단 사유를 `execution_trace`에 기록합니다.
- 존재하지 않는 명시 조문, 기준일이 없는 시점 질문, 근거 부족, 지원되지 않는 인용과 낮은 grounding을 안전한 보류 또는 추가 확인으로 처리합니다.
- 검색 근거가 부족하면 검색 문서 수를 바꾸어 최대 1회만 재시도하고, 개선되지 않으면 `retry_no_improvement`로 중단합니다.
- 기존 `/retrieve`, `/query`, `/answer`는 변경하지 않고 `/agent/runs` 실행·목록·상세 조회 API를 독립적으로 추가합니다.
- 기존 49개 평가 데이터와 호환되는 선택형 workflow·검수 메타데이터를 지원합니다.

## v4.14.1 - 조건부 검토 웹 UI

- 기존 Q&A 답변 카드 안에 조건부 검토 상태와 결론을 표시합니다.
- 쟁점별로 `우선 확인 사실`과 `근거 연결 조치`를 나란히 배치합니다.
- 확인 사실의 `핵심·중요·추가` 우선순위와 연결 근거 조문을 시각적으로 구분합니다.
- V9 API 데이터가 없는 검색·판례 전용 응답에서는 패널을 자동으로 숨깁니다.
- 모바일에서는 두 열을 한 열로 전환하고 기존 답변·법령·판례 카드를 그대로 유지합니다.
- 특정 조직의 내부 업무흐름을 추가하지 않았으며 Q&A 결과 표시 범위만 변경했습니다.

## v4.14.0 - 조건부 검토·중요 사실 우선순위

- 중요 사실이 남아 있으면 답변을 `추가 사실 확인 필요` 상태로 표시하고 최종 법률 판단으로 확정하지 않습니다.
- 쟁점별 확인 사실을 `핵심·중요·추가` 순서로 구조화합니다.
- 확인 사실, 법적 쟁점, 검색 근거와 실무 조치를 감사 가능한 연결 레코드로 제공합니다.
- 기존 `missing_fact_detector`, `practical_action_generator`, 답변 API 필드는 그대로 보존합니다.
- 내부 복수 쟁점 8문항에서 조건부 결론, 우선순위와 사실–쟁점–조치 연결을 결정론적으로 평가합니다.
- 실제 사건의 사실 우선순위나 외부 생성형 LLM의 법률답변 정확도를 보증하지 않습니다.

## v4.14.2 - 복합 법률 영역 웹 예시

- 기존 Q&A 흐름을 유지하면서 `기업법무 복합 검토` 예시 영역 추가
- 직무발명·특허·업무상저작물과 전자금융사고·개인정보 유출 질문을 각 1개씩 노출
- 복합 예시 선택 시 전체 법령, 검색 결과 5개, 답변 모드를 자동 설정
- 특정 조직을 전제로 하지 않는 범용 기업법무 시나리오로 구성

## v4.13.4 - 검증 판례 연결 조문 검색 보강

- 법령 Top-1과 검증 판례의 연결 조문이 불일치할 때 `related_statutes`를 공식 법령 corpus에서 확인해 검색 결과 상단에 보강합니다.
- 보강 조문은 `precedent_linked`와 `판례 연결 조문`으로 표시하여 BM25·시맨틱 검색 결과와 구분합니다.
- 동일 조문의 여러 항을 하나의 조문 카드로 합쳐 민법 제536조 제2항 같은 핵심 하위 근거가 누락되지 않게 했습니다.
- corpus에 본문이 없는 조문은 연결 정보만으로 생성하지 않으며 검색 결과에도 주입하지 않습니다.
- 기존 검색 가중치와 일반 법령 Top-1 랭킹 공식은 변경하지 않았습니다.

## v4.13.3 - 판례 연결 조문 정합성 가드

- 검증 판례가 관련 조문을 명시한 경우 법령 검색 Top-1과 판례 연결 조문의 일치 여부를 검사합니다.
- 불일치하면 해당 법령 결과를 삭제하지 않고 `검색 후보`로 강등하며, 답변은 공식 판례 검증 요약을 사용합니다.
- 원시적·후발적 이행불능 질문에서 민법 제538조가 Top-1으로 검색되던 사례를 회귀 테스트로 고정했습니다.
- 인용 형식의 정확성과 질문에 대한 법적 관련성을 별도 검증 대상으로 관리합니다.

## v4.13.2 - 간결한 근거 기반 웹 답변

- 기존 `answer`와 문장 단위 근거 추적 데이터는 보존하고 웹 표시용 `display_answer`를 추가했습니다.
- 웹 답변을 `결론 → 판단 기준 → 사안 적용 → 유보사항` 순서로 재구성합니다.
- 동일 조문에 연결된 반복 판단과 중복 인용을 제거하고 섹션별 표시 문장 수를 제한합니다.
- 판례가 검색된 질문은 최상위 공식 판례의 핵심 법리를 사안 적용에 함께 표시합니다.
- 기존 API 클라이언트는 `answer`를 계속 사용할 수 있어 하위 호환성이 유지됩니다.

## v4.11.4 - 답변 가독성 개선 패치

- 답변을 결론 → 핵심 체크리스트 → 상세 판단 → 추가 확인 사항 순서로 표시합니다.
- 본문 안의 근거 조문 목록은 숨기고 하단 근거 법령 카드로 통합했습니다.
- `생성 완료` 문구를 `근거 검증 완료`로 변경했습니다.
- 공개 예시 질문 라벨을 법률 실무 중심으로 다듬었습니다.

## v4.11.3 - 답변 생성 정상화 패치

- 유효한 검색 결과가 있음에도 답변이 유보되던 조건을 완화했습니다.
- 저신뢰 검색 결과는 계속 답변 생성을 유보합니다.
- 유보된 결과는 UI에서 검색 후보로 명확히 구분합니다.

## v4.11.2 - 공개 설명 정리 패치

기능 확장 없이 프로젝트의 구조와 검증 범위를 빠르게 이해하도록 공개 화면과 문서를 정리했습니다. 조직 내부 문서 업로드나 미완성 기능은 추가하지 않았습니다.

## v4.11.1 - 공개 데모와 내부 평가 화면 분리

- 공개 데모에서 정량 평가 탭과 전체 평가 실행 버튼을 제거했습니다.
- 품질 검증 철학은 요약 카드로 유지했습니다.
- 내부 평가 콘솔을 `/internal/evaluation` 경로로 분리했습니다.
- 정적 파일 버전 쿼리와 HTML 캐시 방지 헤더를 추가했습니다.

# Patch 64 적용 안내

이 압축 파일은 수정·생성된 파일만 포함합니다.

프로젝트 루트에서 압축을 풀거나, 내부 `law-rag-qa-planner` 폴더의 내용을 기존 프로젝트에 덮어쓰십시오.

## 주요 변경

- 범용 기술 검증용 웹 데모 UI
- 공개 데모 요청 제한
- 공개 환경 평가 실행 차단
- README 전면 한국어화
- 배포 환경변수 예시 추가

## 공개 서버 권장 설정

```bash
LAW_RAG_PUBLIC_DEMO=true
LAW_RAG_ENABLE_EVALUATION_RUN=false
LAW_RAG_DEMO_MAX_REQUESTS=20
LAW_RAG_DEMO_WINDOW_SECONDS=3600
```

## 검증 결과

```text
136 passed
```
## v4.12.0 - 판례 근거 라우팅 및 웹 표시

- 공식 대법원 판례 6건을 법령 corpus와 분리한 전용 retriever 추가
- 해석·적용 표현이 있는 질문에만 판례 검색을 실행하는 evidence router 추가
- API 응답에 `precedent_evidence`, `evidence_routing`을 하위 호환 필드로 추가
- 웹 답변에서 `규범 근거 · 법령`과 `해석·적용 근거 · 판례`를 분리 표시
- 판례 공식 출처, 관련 조문, 법적 맥락·시점 주의사항 표시
- 직접 조문 질문의 판례 미라우팅, 도메인 격리, 사건번호 정답 테스트 추가
## v4.12.1 - 판례 근거 답변과 유보 판단 정합성

- 관련도 0.35 이상인 검증 판례가 있으면 판례 근거 답변 경로를 허용
- 공식 사건번호·출처·판결요약이 빠지거나 임계값 미만이면 기존 유보 유지
- 법령 인용 검증과 판례 근거 검증을 별도 필드로 관리
- 판례 답변에서 결론·판례상 해석·적용상 주의사항·근거 판례를 구조화
- 판례 답변 시 관련성이 낮은 법령 검색 결과를 `관련 법령 검색 후보`로 명시
- 유보 답변의 신뢰도가 높게 표시되던 기존 불일치를 low/0.0으로 수정
- 판례 평가 12문항 Top-1 회귀 테스트 추가(폐쇄형 PoC 결과, 일반화 주장 제외)
## v4.13.0 - 판례 데이터·평가 범위 확장

- 공식 대법원 판례를 6건에서 10건으로 확대
- 개인정보·노동·전자금융·민사계약별 대표 해석 쟁점을 균형 있게 보강
- 판례 평가 문항을 12개에서 20개로 확대
- 근로자성, 개인정보의 재판 제출, 보이스피싱 중대한 과실, 이행불능 구별 평가 추가
- 신규 판례의 관련 조문이 현재 법령 corpus에 존재하는지 자동 검증
- 판례별 검색 별칭과 해석·적용 라우팅 표현 확대
- 폐쇄형 PoC Top-1 회귀 테스트를 20문항으로 확대하고 일반화 한계를 문서화
## v4.13.1 - 웹 검증 시나리오 카탈로그

- 웹 예시 질문을 `법령 직접 확인`과 `판례 해석·적용`으로 분리
- 직접 조문 질문 4개와 판례 질문 6개로 시연 범위 확대
- 새로 추가한 근로자성·개인정보 제출·보이스피싱·이행불능 판례 질문 노출
- 예시 질문 선택 시 적합한 검색 도메인과 답변 모드를 자동 설정
- 선택한 예시 질문을 시각적으로 표시하고 모바일에서 한 열로 재배치
- 현재 corpus에 없는 상법 기반 법인 설립등기 예시는 제거
