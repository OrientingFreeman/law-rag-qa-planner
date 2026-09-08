# RAG·Agent 평가 보고서

## 1. 평가 범위

이 보고서는 `evaluation/datasets/official_core_cases.json`의 동일한 61개 문항으로 Baseline과 Agent Workflow를 비교한 결과입니다. 기존 49개 검색 문항에 안전한 중단·재시도·답변 보류를 검증하는 경계 사례 12개를 추가했습니다.

평가 결과는 법률처럼 정확성과 추적 가능성이 중요한 전문 도메인에서 실행 흐름과 실패 원인을 재현하기 위한 프로젝트 내부 기준선입니다. 법률상담 정확도나 모든 생성형 답변의 정확도를 뜻하지 않습니다.

## 2. 검증된 비교 결과

검증된 소형 결과는 `evaluation/baselines/v4.16.0_baseline_vs_agent_summary.json`에 저장되어 있습니다.

| 구분 | Baseline | Agent Workflow | 변화 |
| --- | ---: | ---: | ---: |
| 전체 통과율 | 59.02% | 68.85% | +9.83%p |
| Top-1 Accuracy | 44.44% | 44.44% | 0.00%p |
| Hit@K / Recall@K | 71.11% | 71.11% | 0.00%p |
| MRR | 0.5348 | 0.5348 | 0.0000 |
| 답변 보류 정확도 | 56.25% | 93.75% | +37.50%p |
| 기대 결과 일치율 | 75.41% | 83.61% | +8.20%p |
| 불필요한 보류율 | 17.78% | 20.00% | +2.22%p |
| 평균 응답시간 | 323.4 ms | 337.2 ms | +13.8 ms |

Agent 적용 후 개선된 사례는 6개, 악화된 사례는 0개였습니다. 다만 이는 이 데이터와 설정에서 관측한 결과이며 다른 모델·corpus·환경에서도 악화가 없다는 보장은 아닙니다.

## 3. 지표 해석

- **검색 품질**: Top-1, Hit@K, MRR은 검색 결과에 정답 조문이 얼마나 앞서 포함되는지 측정합니다.
- **답변·근거 품질**: 필수 근거 포함, 인용 일치, 근거 없는 주장, 추론 품질을 검색 성능과 분리해 판정합니다.
- **Agent 안전성**: 답변 보류 정확도, 불필요한 보류, 필수 사실 누락 탐지, 최대 재시도 준수와 실패 사유 기록을 측정합니다.

검색 지표가 동일한 것은 Agent가 검색기를 새로 교체한 것이 아니라 기존 검색·검증·추론 기능을 통제된 실행 흐름으로 연결했기 때문입니다. 통과율 상승은 주로 안전한 결과 선택과 실패 사유 기록에서 발생했습니다.

불필요한 보류율과 지연시간은 증가했습니다. 따라서 보류 정책을 강화하면 안전성은 높아질 수 있지만 답변 가능한 질문까지 유보하거나 응답시간이 늘어날 수 있습니다.

## 4. 실패와 재시도

경계 사례는 존재하지 않는 조문, 불명확한 적용 기준일, 필수 사실 누락, 충돌 근거, corpus 밖 질문, 비법률 질문, 과도하게 넓은 질문, 잘못된 인용 및 개정 전후 혼동을 포함합니다.

Agent 실행은 최대 재시도 횟수를 설정으로 제한하고, 새 검색어·검색 전략·검색 개수 중 변경 사항을 trace에 기록합니다. 검증 실행에서는 12회 재시도가 발생했지만 재시도 후 품질 개선은 0회였습니다. 이 결과를 숨기지 않으며, 재시도 정책을 정교화할 후속 근거로 사용합니다.

## 5. 재현 명령

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

원시 실험 결과는 `evaluation/experiments/`에 생성되며 Git 추적 대상이 아닙니다. 실행 시각, 데이터셋·코드 버전, 모드, 검색 설정, 재시도·보류 정책, 환경 요약과 문항별 결과가 함께 저장됩니다.

## 6. 한계

- 61개 폐쇄형 데이터셋 결과이며 실제 법률 질의 전체를 대표하지 않습니다.
- 결정론적 provider 실행은 워크플로와 평가 재현성을 확인하기 위한 것이며 상용 LLM 품질 측정치가 아닙니다.
- 지연시간은 실행 환경에 영향을 받습니다.
- 인용 정확도는 답변과 검색 근거가 모두 존재하는 문항에서만 의미가 있습니다.
- 재시도 12건에서 품질 개선이 없었으므로 재시도 횟수 증가를 성능 개선으로 해석할 수 없습니다.
