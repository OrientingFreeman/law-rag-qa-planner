(
echo "============================================================"
echo "TEST 1 - 복합질문"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 2 - 처리위탁 계약"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"개인정보 처리위탁 계약에는 무엇이 포함되어야 하나?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 3 - 국외이전 예외"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"국외 이전 시 별도 동의가 필요 없는 경우는?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 4 - 정의"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"개인정보의 처리위탁이란 무엇인가?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 5 - 비교"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"처리위탁과 제3자 제공의 차이는?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 6 - 시행령"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"처리위탁 계약서에는 어떤 사항을 포함해야 하나?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 7 - 근거조문"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"국외 이전의 근거 조문도 같이 알려줘.",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 8 - Hallucination"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"AI 학습용 개인정보 판매 절차는?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 9 - 개정법"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"2025년 개정 이후 국외 이전 요건은?",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

echo
echo "============================================================"
echo "TEST 10 - 초복합질문"
echo "============================================================"

curl -s -X POST http://127.0.0.1:8000/answer \
-H "Content-Type: application/json" \
-d '{
  "question":"개인정보를 처리위탁하고 해외 클라우드를 사용하며 재위탁도 하는 경우 필요한 절차를 알려줘.",
  "domain":"digital_business",
  "top_k":5
}' | python3 -m json.tool

) | tee output.txt

