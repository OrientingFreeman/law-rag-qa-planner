# Evidence-Grounded Legal AI 프로젝트 요약

## 한 줄 정의

한국 법령의 구조와 시행 시점을 보존한 코퍼스를 기반으로 검색, 근거 할당, 인용 검증, 안전한 유보, 실패 분석과 human review를 연결한 검증 중심 Legal RAG 프로젝트입니다.

## 해결하려는 문제

전문 도메인 RAG는 정답 문서가 검색 결과에 포함되었다는 사실만으로 신뢰할 수 없습니다. 첫 번째 근거가 적절한지, 답변의 문장이 실제 근거와 연결되는지, 인용이 검색 결과에 존재하는지, 질문의 시점과 범위가 충분한지까지 분리해 확인해야 합니다.

이 프로젝트는 다음 질문을 재현 가능한 평가 대상으로 바꿉니다.

- 어떤 법률·조문을 검색했는가?
- gold 근거가 Top-K와 Top-1에 포함됐는가?
- 최종 답변의 주장이 검색 근거와 연결되는가?
- 근거가 부족할 때 답변을 유보했는가?
- 개선 전후의 조건과 데이터가 동일한가?
- 실패 사례를 검수 가능한 데이터로 전환할 수 있는가?

## 현재 구현 범위

| 영역 | 구현 내용 |
| --- | --- |
| 법령 데이터 | 조·항·호 구조, 시행일·개정일, 공식 출처를 보존한 7,516개 문서 |
| 검색 | BM25, 문자 n-gram `semantic_lite`, hybrid 검색과 동일 조건 benchmark |
| 근거 검증 | Semantic Evidence Assignment, 문장 근거 연결, 미지원 인용 탐지 |
| Agent | 10단계 workflow, execution trace, 안전한 유보, 최대 1회 재시도 |
| 평가 | 61개 공식 사례, retrieval·grounding/citation·safety 지표 분리 |
| 데이터 개선 | 실패 기반 hard-negative 후보, human review, versioned export와 checksum |
| Legal Reasoning | Claim–Cause–Element–Defense 기반 schema와 참조 무결성 검증 |
| 배포·검증 | FastAPI, Docker, Python 3.10·3.12 CI, API smoke test |

## 대표 평가 결과

### 검색 비교

공식 평가 데이터 61개 중 gold가 있는 비유보 retrieval 사례 45개를 Top-K 5로 비교했습니다.

| Method | Top-1 | Hit@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 37.78% | 66.67% | 0.4689 | 0.5172 |
| semantic-lite | 46.67% | 73.33% | 0.5748 | 0.6148 |
| hybrid | 46.67% | 75.56% | 0.5730 | 0.6184 |

### Agent 안전성 비교

동일한 61개 사례, deterministic provider, hybrid 검색 조건에서 비교했습니다.

| Metric | Baseline | Agent Workflow |
| --- | ---: | ---: |
| 전체 통과율 | 59.02% | 68.85% |
| 보류 대상 정확도 | 56.25% | 93.75% |
| 전체 outcome 정확도 | 75.41% | 83.61% |
| 불필요한 보류율 | 17.78% | 20.00% |

Agent의 개선은 검색 순위가 아니라 시점 불명, 지원 범위 밖 질문과 거짓 전제의 안전 판정에서 발생했습니다. 재시도 12건에서는 품질 개선이 관측되지 않아 성능 향상 기능으로 주장하지 않습니다.

이 수치는 폐쇄형·결정론적 평가 결과이며 외부 생성형 모델의 자유로운 법률 답변 정확도나 실제 법률 판단 정확도를 의미하지 않습니다.

## 데이터 품질과 재현성

- 평가 사례에 질문 유형, 난이도, gold 법률·조문, 필수 답변 포인트와 유보 여부를 구조화했습니다.
- JSON Schema와 corpus 참조 검증으로 gold 조문의 존재 여부를 확인합니다.
- `retrieval_miss`, `wrong_top1`, `over_retrieval`, `incorrect_abstention`을 독립적으로 기록합니다.
- 자동 발견한 hard negative는 human review를 통과해야 학습 데이터로 export할 수 있습니다.
- dataset, corpus, review와 train/validation split에 checksum을 기록합니다.
- 실행하지 않은 embedding·reranker·fine-tuning 성능은 문서화하지 않습니다.

## Legal Reasoning과 OCR의 현재 경계

Legal Reasoning Schema는 청구권, 청구원인, 요건, 항변, 재항변, 주장·증명책임, 필요 사실, 증거 유형, 후속 질문, 법적 근거와 provenance를 독립 노드 및 관계로 표현합니다. 내부 참조와 JSON round-trip을 검증하지만, 사실→요건 자동 매칭이나 최종 법률 결론을 생성하는 E2E 엔진은 아직 구현하지 않았습니다.

별도 private storage에 보관한 OCR 자료에는 provenance와 quality gate를 적용했습니다. 공개 저장소에는 저작권 원문, 페이지 snippet, private 경로, 검수 큐와 파생 지식베이스를 포함하지 않습니다.

## 검증 상태

v4.27.6에서 다음 명령으로 전체 회귀 테스트를 실행했습니다.

```bash
LAW_RAG_LLM_PROVIDER=deterministic python -m pytest -q
```

결과는 `324 passed, 1 warning in 174.25s`입니다. 경고 1건은 Starlette TestClient/httpx deprecation warning이며 테스트 실패가 아닙니다. GitHub Actions는 Python 3.10·3.12 테스트, 공식 평가 회귀, retrieval 기준선과 Docker API smoke test를 수행합니다.

## 확인 가능한 역량

- 법률 전문지식을 데이터 모델과 검수 규칙으로 변환하는 능력
- RAG 품질을 검색·근거·인용·안전성 지표로 분해하는 능력
- 실패 사례를 숨기지 않고 개선 데이터와 회귀 기준선으로 연결하는 능력
- API, 테스트, Docker와 CI로 실행 가능성을 검증하는 능력
- 저작권·비밀정보와 공개 기술 자산의 경계를 설계하는 능력
- 구현된 기능, 보류된 실험과 미구현 범위를 구분해 설명하는 능력

## 관련 문서

- [프로젝트 README](../README.md)
- [v4.27.6 체크포인트](../PROJECT_CHECKPOINT_V4276.md)
- [최종 검증](FINAL_VERIFICATION.md)
- [Retrieval Benchmark](RETRIEVAL_BENCHMARK.md)
- [Agent Workflow](AGENT_WORKFLOW.md)
- [실험 비교](EXPERIMENT_COMPARISON.md)
- [Legal Reasoning Schema](LEGAL_REASONING_SCHEMA.md)
- [OCR Provenance Audit](OCR_PROVENANCE_AUDIT.md)
