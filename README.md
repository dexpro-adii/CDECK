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

## 📄 License
This project is licensed under the MIT License.
