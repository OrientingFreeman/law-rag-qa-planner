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
