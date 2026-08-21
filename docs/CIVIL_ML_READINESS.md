# 민법 ML 학습·검수 준비도

v4.23은 기존 개인정보보호법 corpus와 공통 회귀평가를 유지하면서 신규 ML 학습
후보의 수동 검수를 `civil_transactions` 도메인부터 시작할 수 있도록 분리합니다.
신규 synthetic 평가 사례나 정답을 만들지 않고 현재 공식 데이터와 실제 retrieval
실패만 사용합니다.

## 자동 준비도 감사

먼저 현재 데이터만 점검할 수 있습니다.

```bash
python -m tools.audit_training_readiness \
  --domain civil_transactions
```

Failure Analyzer 연결과 첫 검수 배치를 함께 확인하려면 실제 benchmark를 넘깁니다.

```bash
python -m tools.run_retrieval_benchmark \
  --methods hybrid \
  --top-k 5 \
  --output evaluation/benchmarks/retrieval_latest.json

python -m tools.audit_training_readiness \
  --domain civil_transactions \
  --benchmark evaluation/benchmarks/retrieval_latest.json \
  --method hybrid \
  --review-limit 20
```

보고서는 다음 gate를 분리합니다.

- 대상 법률 corpus 존재 여부
- retrieval 평가 문항 10건 이상 여부
- 모든 gold 조문이 corpus에서 해소되는지 여부
- 실제 실패에서 후보가 생성되는지 여부
- 수동 검수 필수 및 자동 학습 금지

## 첫 수동 검수 배치 생성

후보 전체를 한꺼번에 검수하지 않고 실패 우선순위와 case ID 순으로 정렬한 뒤
사례당 하나만 선택합니다.

```bash
python -m tools.build_hard_negative_candidates \
  evaluation/benchmarks/retrieval_latest.json \
  --methods hybrid \
  --domains civil_transactions \
  --limit 20 \
  --one-per-case \
  --candidate-pool-version civil-0.1.0
```

개발 서버를 재시작한 뒤 `/internal/training-review`에서 기본 선택된 `민사 거래`
도메인을 검수합니다. Positive는 질문에 직접 답하는 gold 조문인지, Hard negative는
표현이 유사해도 정답 또는 필수 보조 근거가 아닌지를 확인합니다. 애매하거나 gold
자체가 의심되면 승인하지 않고 수정 요청 또는 거절을 선택합니다.

같은 평가 사례에서 여러 오답 문서가 검색된 경우 각 문서는 별도의 후보로 보존되지만
검수 화면은 기본적으로 사례당 하나만 표시합니다. `같은 사례의 추가 후보도 표시`를
선택하면 나머지를 펼칠 수 있고, 후보 버전 필터로 이번 민법 배치만 선택할 수 있습니다.

## 현재 점검 결과

2026-08-20의 공식 61문항 데이터와 Hybrid Top-K 5 실행을 기준으로 확인한 값입니다.

| 항목 | 결과 |
| --- | ---: |
| 민법 도메인 corpus 문서 | 2,043 |
| 고유 법률·조문 | 1,194 |
| 민법 도메인 평가 문항 | 14 |
| retrieval 대상 | 13 |
| 누락된 gold 근거 | 0 |
| 생성 가능한 hard-negative 후보 | 39 |
| 사례당 하나인 첫 검수 배치 | 13 |

13개 후보는 학습 데이터가 아니라 `review_required` 상태의 검수 대상입니다. 승인된
데이터가 충분해진 뒤에만 train/validation 분리와 pretrained baseline, embedding
fine-tuning, reranker 비교를 다음 단계에서 수행합니다.

## 승인 데이터 export와 split 준비

검수한 민법 후보만 별도 dataset version으로 고정합니다. domain과 candidate pool
version을 모두 지정하므로 기존 개인정보보호법 후보나 과거 민법 후보가 섞이지
않습니다.

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

export manifest에는 선택 domain·candidate pool version, 원본 평가 dataset version,
corpus checksum과 승인 건수가 기록됩니다. split 준비는 이 범위가 레코드와
일치하는지 다시 검사하고 동일 평가 사례 또는 query가 train과 validation 양쪽에
들어가지 않도록 합니다. 승인 후보가 없으면 빈 dataset을 만들지 않고 실패합니다.
