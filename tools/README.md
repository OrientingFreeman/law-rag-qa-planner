# 도구 안내

## Agent 실험과 비교

동일한 평가 데이터로 기존 Baseline과 Agent Workflow를 실행하고 비교합니다.

```bash
python tools/validate_evaluation_dataset.py

LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode baseline --dataset evaluation/datasets/official_core_cases.json

LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode agent --dataset evaluation/datasets/official_core_cases.json

python -m tools.compare_rag_experiments \
  evaluation/experiments/{baseline-id}.json \
  evaluation/experiments/{agent-id}.json \
  --output evaluation/experiments/comparison.json
```

원시 결과는 `evaluation/experiments/`에 저장되며 기본적으로 Git에 포함하지 않습니다. 재현 가능한 검증 요약은 `evaluation/baselines/`에 둡니다.

## Retrieval Benchmark

안전성·유보 문항을 제외하고 정답 근거가 지정된 retrieval 문항만 동일한
dataset/corpus version과 Top-K 조건에서 비교합니다.

```bash
python -m tools.run_retrieval_benchmark \
  --methods bm25 semantic_lite hybrid \
  --top-k 5 \
  --output evaluation/benchmarks/retrieval_latest.json
```

실제 Sentence Transformers embedding을 포함하려면 선택 의존성을 설치한 뒤
명시적으로 실행합니다.

```bash
pip install -e '.[ml]'
python -m tools.run_retrieval_benchmark \
  --methods bm25 semantic_lite hybrid pretrained_embedding \
  --embedding-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

`semantic_lite`는 Transformer embedding이 아니라 기존 문자 n-gram cosine
기준선입니다. 결과에는 Top-1 Accuracy, Hit@K, Recall@K, MRR, nDCG@K,
평균 query latency와 index build 시간이 기록됩니다. 원시 결과는
`evaluation/benchmarks/`에 저장하며 기본적으로 Git에 포함하지 않습니다.

Cross-Encoder reranker는 선택한 retriever의 Top-N 결과에만 적용합니다.

```bash
pip install -e '.[ml]'
python -m tools.run_retrieval_benchmark \
  --methods pretrained_embedding pretrained_embedding_reranker \
  --embedding-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --reranker-model BAAI/bge-reranker-v2-m3 \
  --retrieval-top-n 20 \
  --top-k 5
```

fine-tuned checkpoint가 있을 때는 경로를 별도로 지정합니다.

```bash
python -m tools.run_retrieval_benchmark \
  --methods fine_tuned_embedding fine_tuned_embedding_reranker \
  --fine-tuned-embedding-model evaluation/training/checkpoints/legal-retrieval-v1 \
  --retrieval-top-n 20 \
  --top-k 5
```

결과에는 `average_retrieval_latency_ms`와
`average_reranking_latency_ms`가 분리되어 저장됩니다. 실제 실행하지 않은
조합의 성능 수치는 문서화하지 않습니다.

## Retrieval Ablation

모든 검색 조합의 실행 가능 상태를 먼저 기록하고, 완료된 동일 조건 결과만
baseline/treatment로 비교합니다. 기본 동작은 plan-only입니다.

```bash
python -m tools.run_retrieval_ablation

python -m tools.run_retrieval_ablation \
  --methods bm25 semantic_lite hybrid \
  --top-k 5 \
  --execute
```

Pretrained embedding, fine-tuned checkpoint, reranker 조합은 `.[ml]` 의존성과
각 모델 설정이 준비된 환경에서 `--execute`를 명시해야 실행됩니다. 결과는 기존
Experiment Store에 저장되며 미실행·사용 불가능 조합에는 metric이 없습니다.

## Hard-negative 후보와 승인 데이터

```bash
python -m tools.build_hard_negative_candidates \
  evaluation/benchmarks/retrieval_latest.json \
  --methods hybrid \
  --candidate-pool-version 0.1.0

# /internal/training-review에서 training candidate를 검수한 뒤 실행
python -m tools.export_hard_negative_dataset \
  --dataset-version 1.0.0
```

동일 후보는 내용 기반 ID로 중복 저장되지 않습니다. 자동 후보는 항상 검수가
필요하며 승인 이력이 없는 후보는 training dataset으로 export되지 않습니다.

민법부터 10~20건의 첫 수동 검수 배치를 만들 때는 준비도 감사와 도메인 필터를
사용합니다.

```bash
python -m tools.audit_training_readiness \
  --domain civil_transactions \
  --benchmark evaluation/benchmarks/retrieval_latest.json \
  --method hybrid \
  --review-limit 20

python -m tools.build_hard_negative_candidates \
  evaluation/benchmarks/retrieval_latest.json \
  --methods hybrid \
  --domains civil_transactions \
  --limit 20 \
  --one-per-case \
  --candidate-pool-version civil-0.1.0
```

도메인 필터는 기존 후보와 회귀 데이터를 삭제하지 않으며 검수 화면의 표시 범위만
분리합니다.

민법 후보 검수가 끝난 뒤에는 domain과 후보 풀 버전을 고정하여 승인된 레코드만
별도 dataset으로 export합니다.

```bash
python -m tools.export_hard_negative_dataset \
  --domains civil_transactions \
  --candidate-pool-versions civil-0.1.0 \
  --dataset-version civil-1.0.0 \
  --output evaluation/training/civil_hard_negative_dataset.jsonl

python -m tools.prepare_embedding_training \
  --dataset evaluation/training/civil_hard_negative_dataset.jsonl \
  --output-dir evaluation/training/civil_embedding_dataset \
  --seed 42 \
  --validation-ratio 0.2
```

준비된 split 이후 실제 ML 작업의 실행 조건만 점검하려면 다음 gate를 실행합니다.
이 명령은 모델을 다운로드하거나 학습하지 않습니다.

```bash
python -m tools.plan_civil_ml_experiment \
  --prepared-manifest evaluation/training/civil_embedding_dataset/manifest.json \
  --evaluation-dataset evaluation/datasets/official_core_cases.json \
  --checkpoint evaluation/training/checkpoints/civil-retrieval-v1
```

## Embedding Fine-tuning 준비와 실행

승인 dataset의 hash와 review 상태를 검증하고, 동일 query/case가 양쪽 split에
들어가지 않도록 재현 가능한 triplet dataset을 생성합니다.

```bash
python -m tools.prepare_embedding_training \
  --dataset evaluation/training/hard_negative_dataset.jsonl \
  --output-dir evaluation/training/embedding_dataset \
  --seed 42 \
  --validation-ratio 0.2

# 모델을 받거나 학습하지 않고 실행 계획만 Experiment Store에 기록
python -m tools.train_embedding_model \
  --prepared-manifest evaluation/training/embedding_dataset/manifest.json
```

GPU 또는 충분한 CPU 환경에서 실제 학습할 때만 선택 의존성과 `--execute`를
명시합니다.

```bash
pip install -e '.[ml]'
python -m tools.train_embedding_model \
  --prepared-manifest evaluation/training/embedding_dataset/manifest.json \
  --checkpoint-dir evaluation/training/checkpoints/legal-retrieval-v1 \
  --execute
```

계획 단계에는 성능 metric을 기록하지 않습니다. 실제 checkpoint는 동일 retrieval
evaluation set에서 baseline과 별도로 비교해야 합니다.

## 법령 지식베이스 구축·검증

```bash
python tools/build_legal_knowledge_base.py
python tools/validate_legal_knowledge_base.py
python -m pytest tests/test_legal_knowledge_base.py -q
```

## 공식 법령 개정 사례 검증

```bash
python tools/validate_amendment_case_candidates.py
python -m pytest tests/test_amendment_case_candidates.py -q
```

선정된 사례는 현재 코퍼스의 조문, 기존 지식베이스의 개념, 공식 평가
문항과 모두 연결되어야 합니다. 개정 전 본문·개정 후 본문·제정·개정문
링크는 모두 국가법령정보센터의 공식 페이지를 가리켜야 합니다.

선정된 개정 사례의 전체 처리 과정을 실행하려면 다음 명령을 사용합니다.

```bash
python tools/run_k4_amendment_case.py
python -m pytest tests/test_k4_amendment_case.py -q
```

이 명령은 분리된 개인정보 보호법 제15조 개정 전후 fixture를 비교하고,
영향받은 지식베이스 개념과 평가 문항을 추적하며, 2025년 10월 2일 시행일
경계를 평가합니다. 실행 결과로 `data/k4_amendment_impact_manifest.json`과
`docs/AMENDMENT_IMPACT_REPORT.md`를 다시 생성합니다.

## 법령 개정 검수·반영 게이트

```bash
python tools/review_k5_amendment_update.py
python -m pytest tests/test_k5_amendment_review.py -q
```

게이트는 변경할 수 없도록 고정된 개정 영향 manifest의 해시, 공식 출처,
시행일 일관성, 영향 검수 증거, 순서가 지정된 역할별 단계와 테스트 증거를
확인합니다. 판정은 `pass`, `revise`, `reject` 중 하나이며, 사용자가
`pass`를 요청하더라도 필수 조건의 실패를 덮어쓸 수 없습니다.

## 법령 지식베이스 최종 통합 검증

```bash
python tools/run_legal_kb_verification.py
```

이 명령은 지식베이스 검증, 개정 영향 분석, 평가와 검수 게이트를 다시
실행하고 기능별 테스트와 전체 회귀 테스트를 수행합니다. 또한 JSON
데이터에서 공개 문서의 주요 수치를 다시 계산하여 README 또는 프로젝트
요약의 수치가 오래된 경우 전체 검증을 실패로 판정합니다. 실행 결과로
`data/legal_kb_verification.json`과 `docs/LEGAL_KB_VERIFICATION.md`를 다시
생성합니다.

지식베이스 생성기는 사람이 확인할 수 있는 레코드 목록으로부터 검수된
법률용어·일상용어 매핑을 생성합니다. 검증기는 개념 식별자, 관계 유형,
유효기간과 모든 법령·조문·출처 문서 참조를 `data/legal_corpus.json`과
대조합니다.

## 법령 지식베이스 개정 영향 분석

```bash
python tools/analyze_legal_kb_update.py \
  --baseline data/legal_corpus.json \
  --candidate /path/to/candidate_corpus.json \
  --output /tmp/kb_update_manifest.json \
  --mode official_amendment_review
python -m pytest tests/test_legal_kb_update.py -q
```

분석기는 문서의 추가·삭제·본문 변경·시점 메타데이터 변경을 구분하고,
영향받은 법령용어 개념과 공식 평가 문항을 추적합니다. 유효기간이 서로
모순되면 결과를 거부하며, 검수 가능한 업데이트 manifest를 생성합니다.
저장소의 `data/kb_update_manifest.json`은 변경 사항이 없는 기준선의
무결성을 확인한 결과이며, 실제 법령 개정 사례를 처리했다는 의미가
아닙니다.

## 회귀검증 출력 보조 도구

저장된 `/answer` 응답에서 전략 정보를 포함한 요약을 생성하려면 다음
명령을 사용합니다.

```bash
python3 tools/summarize_multi_path.py < answer-response.json > output2.txt
```

요약 결과에는 `confidence`와 `recommendation_score`뿐 아니라
`recommendation_reasons`와 `strategy_profile`도 의도적으로 포함됩니다.
따라서 간략한 회귀검증 출력에서도 전략 계층의 필드가 누락되지 않습니다.
