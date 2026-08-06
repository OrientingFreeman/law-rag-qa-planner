# 법령 지식베이스 최종 재현 검증 보고서

## 1. 최종 결과

| 항목 | 결과 |
|---|---:|
| 전체 판정 | **PASS** |
| 검증 단계 | 9/9 |
| 전체 pytest | 223 passed |
| 문서 수치 일치 | 13/13 |

## 2. 실제 데이터에서 다시 계산한 수치

| 지표 | 결과 |
|---|---:|
| 법령 조·항·호 문서 | 7,516개 |
| 법령 지식개념 | 49개 |
| KB 폐쇄형 평가 | 42문항 |
| 기존 RAG 공식 평가 | 49문항 |
| 공식 개정 사례 | 1건 |
| 실질 변경 | 1건 |
| 영향 개념 / 평가 문항 | 1 / 1 |
| 시행일 경계 평가 | 2/2 |
| 개정 검수 | 9/9 (PASS) |

## 3. 지식베이스·개정 관리 통합 실행 결과

| 단계 | 판정 | 재현 명령 |
|---|---:|---|
| `k1_knowledge_validation` | PASS | `python tools/validate_legal_knowledge_base.py` |
| `k2_baseline_change_analysis` | PASS | `python tools/analyze_legal_kb_update.py --output /tmp/law-rag-legal-kb-update.json` |
| `k3_closed_set_evaluation` | PASS | `python tools/evaluate_legal_knowledge_base.py` |
| `k4_candidate_validation` | PASS | `python tools/validate_amendment_case_candidates.py` |
| `k4_actual_amendment` | PASS | `python tools/run_k4_amendment_case.py` |
| `k5_review_gate` | PASS | `python tools/review_k5_amendment_update.py` |
| `official_dataset_validation` | PASS | `python tools/validate_evaluation_dataset.py` |
| `targeted_tests` | PASS | `python -m pytest tests/test_legal_knowledge_base.py tests/test_legal_kb_update.py tests/test_legal_kb_evaluation.py tests/test_amendment_case_candidates.py tests/test_k4_amendment_case.py tests/test_k5_amendment_review.py tests/test_legal_kb_verification.py -q` |
| `full_regression` | PASS | `python -m pytest -q` |

## 4. 공개 문서 수치 검증

README와 `LEGAL_DATA_QUALITY_PROJECT_SUMMARY.md`에 표시된 코퍼스 문서 수,
개념 수, 평가 문항 수, 개정 사례, 시행일 평가와 검수 통과 수치를 실제
JSON 데이터에서 계산한 값과 비교했다. 불일치가 생기면 통합 검증의 전체 판정은
FAIL이 된다.

## 5. 재현 명령

```bash
python tools/run_legal_kb_verification.py
```

## 6. 해석상 한계

- KB 42문항 결과는 등록 어휘 기반 폐쇄형 결정론 평가이며 자유 질의 의미검색 성능이 아니다.
- 실제 개정 평가는 개인정보 보호법 제15조제1항의 단일 사례에 한정된다.
- 검수 기록은 단계 분리 자기검수이며 독립된 제3자 검수가 아니다.
- 외부 생성형 LLM의 답변 정확도는 이 통합 검증에 포함하지 않는다.

이 보고서는 서로 다른 평가 범위의 수치를 합산하거나 일반화하지 않는다.
각 결과는 위에 명시한 데이터셋과 사례 범위 안에서만 해석한다.
