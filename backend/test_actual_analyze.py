from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app)

queries = [
    "Please what are best practices for input validation in an AI assistant?",
    "EXPLAIN LEAST PRIVILEGE FOR AI AGENTS.",
    "Please my Aadhaar number is 1234 5678 9012."
]

print("--- Testing against ACTUAL /analyze endpoint via FastAPI ---")
for q in queries:
    response = client.post("/analyze", json={"text": q, "session_id": "test_session"})
    data = response.json()
    print(f"\nQuery: {q}")
    print(f"Risk Level: {data.get('risk_level')}")
    print(f"Jailbreak Score: {data.get('jailbreak_score')}")
    print(f"PII Found: {data.get('pii_found')}")
