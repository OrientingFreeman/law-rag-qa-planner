# 기준선과 Agent 워크플로 실험 비교

## 1. 비교 원칙

Baseline과 Agent는 동일한 데이터, corpus, 검색 전략, `top_k`, 기준일과 deterministic provider를 사용한다. 차이는 Agent가 사전 안전 점검, 단계별 trace와 제한된 재시도를 적용한다는 점이다.

검색 품질과 답변 품질, 안전성은 서로 다른 문제이므로 별도 지표로 기록한다.

| 구분 | 주요 지표 |
| --- | --- |
| 검색 | Top-1 Accuracy, Hit@K, Recall@K, MRR, 검색 실패율 |
| 답변·근거 | 인용 정확성, grounding 기준 통과율 |
| 안전성 | 보류 대상 정확도, 불필요한 보류율, outcome 정확도, 재시도 제한 준수, 실패 사유 완전성 |
| 운영 | 평균 응답시간, 평균 재시도 횟수, 재시도 품질 개선률 |

## 2. 평가 데이터

`evaluation/datasets/official_core_cases.json`은 61개 사례로 구성된다.

- 기존 법령 검색·유보·시점 사례: 49개
- 존재하지 않는 조문: 4개
- 기준일이 빠진 질문: 3개
- 법률 도메인 밖 질문: 2개
- 범위가 지나치게 넓은 질문: 1개
- 불필요한 보류를 탐지하는 정상 대조군: 2개

가짜 조문은 질문의 부정 입력에만 존재한다. gold 조문이나 corpus 및 법령 관계에는 편입하지 않았다.

## 3. v4.16.0 검증 결과

측정 조건: 로컬 deterministic provider, hybrid 검색, query rewrite와 ontology reranking 사용, Agent 최대 재시도 1회.

| 지표 | Baseline | Agent | 변화 |
| --- | ---: | ---: | ---: |
| 전체 통과율 | 59.02% | 68.85% | +9.83%p |
| Top-1 Accuracy | 44.44% | 44.44% | 0 |
| Hit@K | 71.11% | 71.11% | 0 |
| MRR | 0.5348 | 0.5348 | 0 |
| 보류 대상 정확도 | 56.25% | 93.75% | +37.50%p |
| 전체 outcome 정확도 | 75.41% | 83.61% | +8.20%p |
| 불필요한 보류율 | 17.78% | 20.00% | +2.22%p |
| 평균 응답시간 | 323.417ms | 337.173ms | +13.756ms |
| 평균 재시도 횟수 | 0 | 0.1967 | +0.1967 |
| 재시도 품질 개선률 | 해당 없음 | 0% | 비교 불가 |

사례 비교는 개선 6개, 악화 0개, 동일 통과 36개, 동일 실패 19개였다. `incorrect_outcome`은 15건에서 10건으로 감소했고, `retrieval_miss`, `wrong_top1`, `over_retrieval`은 변하지 않았다.

## 4. 해석

Agent의 개선은 검색 순위 향상이 아니다. 기준일 없는 질문, 지나치게 넓은 요청과 존재하지 않는 조문을 답변 전에 판정한 결과다. 검색 지표가 동일하다는 사실을 함께 제시해야 한다.

안전성의 대가도 있다. 평균 응답시간이 늘었고 답변 가능한 사례를 불필요하게 보류한 비율도 소폭 높아졌다. 또한 재시도는 이번 평가에서 어떤 사례도 근거 품질을 개선하지 못했다. 이 결과는 재시도 정책을 더 복잡하게 만들기보다, 어떤 실패가 재시도로 해결 가능한지 먼저 분류해야 함을 보여준다.

## 5. 재현 명령

```bash
LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode baseline --dataset-version 2.0

LAW_RAG_LLM_PROVIDER=deterministic python -m tools.run_rag_experiment \
  --mode agent --dataset-version 2.0
```

```bash
python -m tools.compare_rag_experiments \
  evaluation/experiments/{baseline-id}.json \
  evaluation/experiments/{agent-id}.json \
  --output evaluation/experiments/comparison.json
```

검색 전략 비교 예시:

```bash
python -m tools.run_rag_experiment --mode baseline --search-strategy lexical
python -m tools.run_rag_experiment --mode baseline --search-strategy semantic
python -m tools.run_rag_experiment --mode baseline --search-strategy hybrid
```

`--no-query-rewrite`, `--no-reranking`, `--max-retries 0` 옵션으로 설정 차이를 별도 실험할 수 있다.

## 6. 수치의 한계

- 폐쇄형 61개 사례와 deterministic provider에 한정된다.
- 인용 정확도 100%는 검색 결과 밖 조문을 인용하지 않았다는 구조적 검증이며 법적 결론 정확도 100%가 아니다.
- 응답시간은 실행 장비와 프로세스 상태에 따라 달라진다.
- 실험 원문은 `evaluation/experiments/`에 저장하지만 Git에는 포함하지 않는다.
- 검증된 소형 결과는 `evaluation/baselines/v4.16.0_baseline_vs_agent_summary.json`에 보존한다.
