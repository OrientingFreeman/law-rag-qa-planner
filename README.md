# 법령 문서 기반 RAG QA 시스템 데이터 기획 및 미니 구현

## 1. 프로젝트 개요

본 프로젝트는 법령 문서를 기반으로 한 RAG(Retrieval-Augmented Generation) QA 시스템의 데이터 구조, 검색 전략, 프롬프트 설계, 평가 지표를 설계하고 간단히 구현한 미니 프로젝트입니다.

법령 영역에서는 LLM이 단독으로 답변할 경우 환각, 출처 불명확, 최신 개정 반영 오류가 발생할 수 있습니다. 따라서 법령 데이터를 조문 단위로 구조화하고, metadata 기반 필터링과 검색 전략을 결합하여 근거 기반 답변을 생성하는 구조가 필요합니다.

## 2. 문제 정의

법령 QA 시스템에서 중요한 문제는 다음과 같습니다.

- 정확한 조문 검색
- 개정일 및 시행일 반영
- 근거 없는 답변 생성 방지
- 출처와 조문 번호 명시
- 검색 실패 및 환각 케이스 관리

## 3. 데이터 구조 설계

각 법령 데이터는 다음과 같은 metadata를 포함합니다.

- document_type
- law_name
- article_no
- clause_no
- item_no
- effective_date
- revision_date
- authority
- reliability
- topic
- keywords
- content

## 4. Chunking 전략

일반 문서처럼 길이 기준으로 chunking하지 않고, 법령의 의미 구조에 맞춰 조문 단위 chunking을 사용합니다.

기본 단위는 조문(article)이며, 필요한 경우 항(clause), 호(item) 단위로 세분화할 수 있습니다.

## 5. Retrieval 전략

본 미니 구현에서는 간단한 keyword 기반 검색을 사용했지만, 실제 서비스에서는 다음 구조로 확장할 수 있습니다.

1. 사용자 질문 분석
2. 법령명, 주제, 조문번호 기반 metadata filtering
3. semantic vector search
4. keyword search
5. reranking
6. 근거 문서 선택
7. LLM 답변 생성

## 6. Prompt 설계

LLM 답변 생성 단계에서는 다음 원칙을 적용합니다.

- 제공된 근거 문서만 사용
- 근거에 없는 내용은 추측 금지
- 법령명과 조문 번호 명시
- 근거 부족 시 fallback 응답

## 7. Evaluation 설계

단순 정답률이 아니라 다음 지표를 함께 평가해야 합니다.

- retrieval accuracy
- answer grounding
- hallucination rate
- source completeness
- freshness

## 8. 실행 방법

```bash
python src/chunking.py
python src/retriever.py
python src/prompt_builder.py
python src/evaluation.py
```

## 11. Evaluation 결과

샘플 데이터 기반 테스트 결과:

- Retrieval Accuracy: 1.00 (3/3)
![architecture](./images/accuracy_test1.png)
※ 단, 본 결과는 제한된 샘플 데이터 기준이며, 실제 서비스에서는 더 다양한 질의와 대규모 데이터셋 기반 평가가 필요할 것으로 보임.


## 12. Failure Case Analysis

본 프로젝트에서는 단순히 정답을 맞추는 것이 아니라, retrieval 단계에서 발생할 수 있는 failure case를 재현하고 그 원인과 개선 방향을 분석하였다.

---

### Failure Case 1: 법령명 누락 (Missing Law Name)

**Query**

손해배상 책임 요건은 무엇인가?

I. 실험결과

해당 질의에 대한 retrieval 결과:

Top results: 제750조, 제390조
Hit@K 기준에서는 정답 포함 (Hit)
그러나 복수의 후보 조문이 함께 검색됨
![architecture](./images/accuracy_test2.png)

II. 문제 원인

질의에 법령명(민법)이 명시되지 않음
"손해배상" 키워드는 불법행위(제750조)와 채무불이행(제390조) 모두에서 사용됨
keyword 기반 retrieval만으로는 법적 맥락(disambiguation)을 구분하기 어려움

III. 의미

Hit@K 기준에서는 성능이 높게 측정될 수 있으나,
실제 서비스에서는 Top-1 정확도 저하 및 잘못된 조문 선택 가능성 존재

IV. 개선방향

query intent 분석을 통한 법령명 및 주제 추론
semantic search 도입 (embedding 기반 의미 유사도 활용)
query expansion 적용
(예: "손해배상" → "불법행위 손해배상")
reranking 단계에서 법적 맥락 반영

### Failure Case 2: 유사 키워드 충돌

Query:
손해배상 청구 규정은?

Expected:
민법 제390조

![architecture](./images/accuracy_test3.png)

I. 실험 결과
keyword 기반 retrieval에서는 "손해배상" 키워드가 포함된 민법 제750조가 Top-1으로 선택되었다.

II. 문제 원인
민법 제750조와 제390조는 모두 "손해배상"과 관련되지만,
제750조는 불법행위 책임, 제390조는 채무불이행 책임에 관한 조문이다.
단순 keyword matching은 "청구"라는 법적 맥락을 충분히 반영하지 못한다.

III. 의미
Hit@K 기준에서는 정답 조문이 포함될 수 있지만,
Top-1 기준에서는 잘못된 조문이 선택될 수 있다.


## 13. 간단실행 결과
![architecture](./images/demo_output1.png)


## 14. Retrieval Evaluation (Sample)

본 프로젝트에서는 retrieval accuracy를 평가하기 위해 테스트 쿼리셋을 구성하고,
expected article 기준으로 hit 여부를 측정하는 구조를 설계했습니다.

### Sample Test Cases

| Query | Expected Article | Hit 여부 |
|------|----------------|----------|
| 민법상 불법행위 손해배상 요건은? | 제750조 | Hit |
| 채무불이행 손해배상 규정은? | 제390조 | Hit |
| 개인정보 수집 요건은? | 제15조 | Hit |

※ 본 결과는 샘플 데이터 기반 테스트이며,
실제 서비스에서는 더 큰 데이터셋과 다양한 질의에 대한 평가가 필요합니다.


