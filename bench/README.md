# PromptKavach Evaluation Benchmark 🛡️

This directory contains the frozen evaluation suite for PromptKavach.

## Structure

- `benchmark_cases.json`: Frozen benchmark dataset with labeled test cases.
- `run_benchmark.py`: Standalone evaluation runner reporting recall and granular false-positive rates.

## Categories Evaluated

### 1. Adversarial Cases (Label 1)
- `instruction_override`: Direct instructions to ignore or bypass previous directives.
- `role_play`: Personas designed to bypass safety boundaries (DAN, Developer Mode, etc.).
- `hypothetical`: Theoretical and hypothetical scenarios seeking harmful content.
- `academic_evasion`: Educational framing for illicit payloads.
- `hinglish_override`: Hindi-English code-mixed prompt injections and bypasses.
- `data_exfiltration`: Attempts to extract other users' records or credentials.
- `system_prompt_leak`: Extraction of underlying system prompt and configuration.

### 2. In-Category Benign Hard Negatives (Label 0)
- `coding_request`: Legitimate technical and script generation requests.
- `greeting_smalltalk`: Casual greetings and polite opening queries.
- `weather`: Natural inquiries regarding forecasts and temperatures.
- `summarization`: Document and email condensation requests.
- `troubleshooting`: Programming error messages and debugging inquiries.
- `timezone`: Time, date, and timezone calculations.
- `educational_security`: AI safety research questions discussing prompt injection defensively.
- `pii_handling`: Legitimate discussions containing masked/redacted PII examples.

### 3. Out-of-Category Benign Hard Negatives (Label 0)
Diverse, general-domain questions outside the 6 initial training categories:
- `health_wellness`: Sleep, hydration, exercise, allergies, ergonomics.
- `travel_planning`: Itineraries, packing advice, cultural etiquette, transit.
- `cooking_culinary`: Recipes, culinary techniques, ingredient substitutes, fermentation.
- `personal_finance`: Budgeting, retirement accounts, index funds, debt payoff.
- `relationship_advice`: Interpersonal communication, active listening, conflict resolution.
- `general_trivia`: History, astronomy, geography, atmospheric science, physics.

## Execution

From repository root:
```bash
python bench/run_benchmark.py
```
Or using the backend environment:
```powershell
.\backend\fresh_venv\Scripts\python.exe bench/run_benchmark.py
```
