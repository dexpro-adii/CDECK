# PromptKavach 🛡️

PromptKavach is a comprehensive, AI-driven security middleware designed to protect Large Language Model (LLM) applications from vulnerabilities, adversarial attacks, and data leaks. It acts as a robust shield between users and your core AI systems, ensuring safe, compliant, and reliable interactions.

## 🚀 Features

- **Jailbreak & Prompt Injection Detection:** Advanced classifiers using `sentence-transformers` and heuristics to block malicious instructions, role-play bypasses, and system prompt extraction attempts.
- **PII Detection & Redaction:** Leverages Presidio to automatically detect and redact sensitive Personally Identifiable Information (PII) including UPI IDs, IFSC codes, emails, and phone numbers.
- **Output Guardrails:** Scans LLM responses to ensure no sensitive information or harmful content is leaked back to the user.
- **Agentic Tool Security:** Monitors tool-calling behavior to prevent unauthorized access or indirect prompt injections.
- **Secondary Review (Gemini):** Optional on-demand deep review using Gemini for complex, ambiguous, or multi-lingual (e.g., Hinglish) inputs.
- **Session & Context Tracking:** Tracks user sessions over time to detect multi-turn attacks and contextual manipulation.

## 🛠️ Tech Stack

### Backend
- **Framework:** FastAPI (Python)
- **Machine Learning:** `scikit-learn`, `sentence-transformers` (all-MiniLM-L6-v2)
- **PII Detection:** Microsoft Presidio Analyzer & Anonymizer
- **LLM Integration:** Google Gemini API / Ollama

### Frontend
- **Framework:** React 19 + Vite
- **Styling:** Tailwind CSS + Lucide React
- **UI/UX:** Dynamic 3D backgrounds and animations (Three.js integration)

## 📦 Getting Started

### Prerequisites
- Node.js (v18+)
- Python (3.9+)

### Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Download the required spaCy model for Presidio PII analysis:
   ```bash
   python -m spacy download en_core_web_lg
   ```

## Environment variables
Create backend/.env with a Google Gemini API key (required for hybrid deep-review escalation):
```bash
GOOGLE_API_KEY=your_key_here
```
Get a key at https://aistudio.google.com/apikey. Without this, the app still runs, but medium-risk/code-mixed prompts will not get escalated by Gemini review — they'll fall back to the local pipeline's own verdict.

5. Run the backend server:
   ```bash
   python -m uvicorn main:app --reload
   ```

## Optional: GPU acceleration
By default, `pip install -r requirements.txt` installs CPU-only PyTorch.
If you have an NVIDIA GPU, install the CUDA build afterward:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124 --force-reinstall
```
Verify with: python -c "import torch; print(torch.cuda.is_available())"

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

## 🛡️ Architecture
PromptKavach intercepts incoming prompts, passing them through a series of specialized detectors (PII, Jailbreak, Time-based, Tool Security). If a prompt is flagged as high-risk, it is either blocked immediately or passed to a secondary LLM for deeper analysis. Safe prompts are allowed through to your core application.

## 🔐 Vault key custody

The session PII vault (`backend/vault.py`) holds the original Aadhaar / PAN / UPI
values behind the `<TYPE_n>` placeholders so `/vault/resolve` can restore them
for the authorised caller.

### Current state

- Values are stored **encrypted** (Fernet / AES-128-CBC + HMAC), never as plaintext.
- The key comes from `PROMPTKAVACH_VAULT_KEY`. Generate one with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- If that variable is unset the service generates an **ephemeral** key and logs a
  warning. Vaulted values then do not survive a restart — deliberately chosen so
  the failure mode is "unreadable" rather than "silently readable".
- **Rotation path:** move the current key into `PROMPTKAVACH_VAULT_RETIRED_KEYS`
  (comma-separated) and put a new one in `PROMPTKAVACH_VAULT_KEY`. Every loaded
  key can decrypt; the first one encrypts. `SessionVault.rotate()` re-encrypts
  everything in place.
- Entries expire after `DEFAULT_TTL_SECONDS` (1 h) and the number of retained
  sessions is capped, so PII no longer accumulates for the life of the process.
- No key material is committed; a test fails the build if a key-shaped literal
  appears in `vault.py`.
- **`/vault/resolve` is authenticated.** Each session gets a 32-byte bearer
  secret, minted on first write and returned as `session_token` by `/vault/mask`
  and `/analyze-content`. Resolving requires it in the `X-Vault-Token` header:

  ```bash
  curl -X POST localhost:8000/vault/resolve \
       -H "X-Vault-Token: <session_token>" \
       -H "Content-Type: application/json" \
       -d '{"session_id": "...", "masked_text": "..."}'
  ```

  Comparison is constant-time. A wrong token and an unknown session return an
  identical 401, so the endpoint cannot be used to enumerate live session ids.
  Secrets are dropped when their session expires.

### Known gaps — NOT production ready

This is hackathon-grade hardening. Do not ship it as-is:

1. **The key lives in the process environment.** Anyone who can read the process,
   its environment, or a core dump gets the key and therefore every vaulted value.
2. **Session tokens are bearer credentials.** Anyone who captures one can resolve
   that session until it expires. There is no binding to a user identity, no
   revocation, and no refresh — a real deployment needs the session bound to an
   authenticated principal (OIDC / mTLS), not just to a secret string.
3. **Storage is per-process memory.** Multiple workers do not share a vault, so
   resolution fails behind a load balancer.
4. **No audit trail.** There is no record of which caller resolved which token.
5. **No envelope encryption.** One key protects every value; compromise is total.

### What real hardening would look like

| Gap | Production approach |
|---|---|
| Key custody | KMS-held root key (AWS KMS / GCP KMS / HashiCorp Vault); the process never sees raw key material and calls `Decrypt` per operation |
| Key scope | Envelope encryption — a per-session data key wrapped by the KMS root key, so one leaked data key exposes one session |
| Rotation | Scheduled automatic rotation with versioned key ids stored alongside each ciphertext; re-wrap as a background job |
| Resolve auth | Bind each session to an authenticated principal (OIDC / mTLS) rather than a bearer string, with revocation and short-lived refresh |
| Storage | Shared encrypted store (Redis/Postgres) with server-side TTL, so workers share state |
| Audit | Append-only log of every mask/resolve with principal, token id and timestamp, shipped off-box |
| Blast radius | Per-tenant keys so one tenant's compromise cannot decrypt another's |

## 📊 Performance

Measured with `backend/scripts/benchmark_rails.py` on the development machine
(Windows, Python 3.14, CPU inference, no GPU). Numbers are milliseconds.

**Per-rail cost, single thread, 100 iterations:**

| Rail | p50 | p95 | p99 |
|---|---|---|---|
| PII detect (input rail) | 3.71 | 5.95 | 6.18 |
| Jailbreak detect (input rail) | 7.71 | 11.57 | 12.48 |
| Output rail (`scan_output`) | 13.24 | 15.37 | 16.63 |

The output rail is the most expensive because it runs *both* of the other two
over the generated response.

**End-to-end over HTTP, real uvicorn server:**

| Endpoint | conc | p50 | p95 | p99 | req/s |
|---|---|---|---|---|---|
| `/analyze` (full pipeline) | 1 | 35.8 | 40.0 | 43.2 | 27.7 |
| `/analyze` (full pipeline) | 8 | 266.5 | 290.2 | 377.8 | 29.7 |
| `/analyze` (full pipeline) | 16 | 543.6 | 914.9 | 1714.2 | 25.4 |
| `/analyze-content` (retrieval) | 1 | 17.6 | 19.6 | 21.4 | 56.4 |
| `/analyze-content` (retrieval) | 16 | 259.6 | 437.6 | 814.0 | 53.9 |
| `/check-tool-call` (execution) | 1 | 6.6 | 7.7 | 8.0 | 148.7 |
| `/check-tool-call` (execution) | 16 | 79.7 | 92.0 | 153.0 | 192.4 |
| `/vault/mask` | 1 | 6.7 | 7.7 | 8.3 | 147.5 |

**Reading the numbers:** throughput is flat at ~29 req/s for `/analyze` no matter
how many clients pile on, while latency scales linearly with concurrency. The
detectors are synchronous CPU work called from `async def` handlers, so they
block the event loop and the service is effectively serialised. Fixing that means
moving the detector calls into a thread/process pool (`run_in_executor`) — the
single highest-leverage performance change available, and not yet done.

## 📄 License
This project is licensed under the MIT License.
