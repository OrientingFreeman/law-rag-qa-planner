# 기업 법무 질문 RAG 검색 평가

## 평가 목적

결제·전자금융, 개인정보, 기술·지식재산 질문 12건이 실제 하이브리드
검색 파이프라인에서 사전에 지정한 법률·조문을 회수하는지 평가한다.
법령용어–일상용어의 명시적 매핑을 확인하는 KB 폐쇄형 평가와 달리,
이 평가는 질의 계획, 도메인 확장, 검색·재정렬·유보 판단을 포함한다.

## 전후 결과

| 지표 | 규칙 보강 전 | 보강 후 |
|---|---:|---:|
| 통과 | 8/12 | 12/12 |
| Pass rate | 66.67% | 100.00% |
| Top-1 Accuracy | 58.33% | 100.00% |
| Hit@5 | 83.33% | 100.00% |
| Recall@5 | 83.33% | 100.00% |
| MRR | 0.6833 | 1.0000 |
| 유보 판단 정확도 | 75.00% | 100.00% |

초기 기준선에서는 처리위탁·유출 통지, 전자금융사고 책임, 업무상 프로그램
저작자 질문에서 검색 누락 또는 과도한 유보가 발생했다. 법령 정답을 검색
결과에 직접 고정하지 않고, 각 도메인의 동의어와 쟁점별 질의 확장 규칙을
보강했다. 또한 특허출원 전 공개 질문은 신규성 원칙인 제29조뿐 아니라
공지예외인 제30조도 함께 검토해야 한다는 법적 검수 결과를 반영해 gold
조문을 보정했다. 따라서 전후 차이는 검색 규칙 개선과 평가 정답 보정이
함께 반영된 결과다.

## 문항별 결과

| case_id | 통과 | Top-1 | Hit@5 | 정답 근거 | 진단 |
|---|---:|---:|---:|---|---|
| `business-eft-transaction-confirmation` | PASS | Y | Y | 010199:제7조 | over_retrieval |
| `business-eft-error-correction` | PASS | Y | Y | 010199:제8조 | over_retrieval |
| `business-eft-terms-disclosure` | PASS | Y | Y | 010199:제24조 | over_retrieval |
| `business-eft-dispute-handling` | PASS | Y | Y | 010199:제27조 | over_retrieval |
| `business-eft-accident-liability` | PASS | Y | Y | 010199:제9조 | over_retrieval |
| `business-eft-record-retention` | PASS | Y | Y | 010199:제22조 | over_retrieval |
| `business-pipa-processing-delegation` | PASS | Y | Y | 011357:제26조 | over_retrieval |
| `business-pipa-breach-notice` | PASS | Y | Y | 011357:제34조 | over_retrieval |
| `business-ip-patent-novelty` | PASS | Y | Y | 001455:제29조, 001455:제30조 | over_retrieval |
| `business-ip-disclosure-exception` | PASS | Y | Y | 001455:제30조 | over_retrieval |
| `business-ip-employee-invention` | PASS | Y | Y | 000312:제2조 | over_retrieval |
| `business-ip-work-made-for-hire` | PASS | Y | Y | 000798:제9조 | over_retrieval |

## 진단 항목

| 유형 | 현재 건수 |
|---|---:|
| `over_retrieval` | 12건 |

`over_retrieval`은 정답 조문을 모두 찾았더라도 Top-K에 정답 외 후보가 함께
포함된 경우를 기록하는 진단 항목이다. 이 데이터셋은 실무 검토에서 관련
후보를 함께 살피는 검색 환경을 가정해 Top-K를 5로 유지했으므로, 이를
답변 오류나 평가 실패와 동일하게 해석하지 않는다.

## 재현 명령

```bash
python tools/evaluate_business_legal_cases.py
```

## 해석상 한계

- 12문항은 공개 법령을 사용한 내부 설계 평가이며 독립된 제3자 블라인드 평가가 아니다.
- Hit@5 100%는 정답 조문이 상위 5개 안에 포함됐다는 뜻이며, 생성형 답변의 법적 정확도를 뜻하지 않는다.
- 계약 협상, 소송 수행, 특허출원·권리관리 실무 능력을 직접 평가하지 않는다.
- 구체적인 출원 가능성, 책임 성립과 권리귀속은 추가 사실관계와 전문가 검토가 필요하다.
