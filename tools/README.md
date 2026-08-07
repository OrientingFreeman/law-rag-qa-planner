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
