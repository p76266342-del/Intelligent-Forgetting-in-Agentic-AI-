# Intelligent Forgetting in Agentic AI

### Next.js + TypeScript + Tailwind + FastAPI + Firebase + Gemini + Qdrant + Reinforcement Learning + Render

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-App%20Router-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19.0%2B-61DAFB.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8%2B-3178C6.svg)](https://www.typescriptlang.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4%2B-38B2AC.svg)](https://tailwindcss.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Semantic%20Retrieval-DC2626.svg)](https://qdrant.tech/)
[![Google Gemini](https://img.shields.io/badge/Google%20GenAI-Gemini%202.5%20Flash-4285F4.svg)](https://ai.google.dev/)
[![Firebase](https://img.shields.io/badge/Firebase-Auth%20RBAC-FFCA28.svg)](https://firebase.google.com/)
[![Tests](https://img.shields.io/badge/pytest-58%20passed-success.svg)](backend/tests/)

---

## 1. Project Overview & Motivation

Autonomous AI agents operating over extended horizons encounter **cognitive saturation**:
1. **Context Window Saturation**: Long conversation histories exhaust token budgets and inflate inference latency and cost.
2. **Signal-to-Noise Degradation**: Ephemeral scratchpad logs and conversational chatter dilute foundational system constraints and user preferences.
3. **Catastrophic Forgetting**: Naive First-In-First-Out (FIFO) or Least-Recently-Used (LRU) pruning discards foundational constraints simply because they were established early.

**Intelligent Forgetting in Agentic AI** solves this dilemma through a biologically-inspired, multi-tiered cognitive memory lifecycle. Rather than unbounded memory accumulation or naive truncation, the platform intelligently decides what information to:
- 🟢 **KEEP**: Retain high-utility, task-relevant, or frequently accessed knowledge.
- 🟣 **COMPRESS**: Synthesize and merge semantically redundant memories into compact summaries with provenance tracking.
- 🟡 **ARCHIVE**: Move lower-priority memories to cold storage outside active LLM context, searchable on-demand via Qdrant.
- 🔴 **PRUNE**: Permanently eradicate low-scoring, outdated memories to liberate working context capacity.

The platform pairs this cognitive architecture with a **LinUCB Contextual Bandit Reinforcement Learning Engine** to optimize memory lifecycle actions over time using empirical rewards, subject to strict mathematical safety constraints.

---

## 2. Target Project Structure

```
ai/
├── backend/                                   # Python FastAPI Backend
│   ├── src/
│   │   └── intelligent_forgetting/
│   │       ├── __init__.py
│   │       ├── api.py                         # REST & SSE streaming endpoints
│   │       ├── agent.py                       # Autonomous agent simulation
│   │       ├── auth.py                        # Firebase Admin & token verification
│   │       ├── config.py                      # Pydantic Settings configuration
│   │       ├── forgetting_engine.py           # Multi-factor cognitive forgetting engine
│   │       ├── gemini_service.py              # Official Google Gen AI SDK integration
│   │       ├── memory_scorer.py               # Mathematical multi-factor utility scorer
│   │       ├── memory_store.py                # Thread-safe SQLite relational database
│   │       ├── models.py                      # Pydantic v2 domain schemas
│   │       ├── rl_engine.py                   # LinUCB Contextual Bandit RL engine
│   │       └── vector_store.py                # Qdrant semantic vector integration
│   ├── tests/                                 # Pytest test suite (58 automated tests)
│   ├── experiments/                           # Reproducible 4-way empirical benchmark
│   ├── docs/                                  # Architecture & methodology documentation
│   ├── pyproject.toml                         # Backend package specification
│   ├── pytest.ini                             # Pytest configuration
│   ├── requirements.txt                       # Python dependencies
│   └── .env.example                           # Backend environment template
├── frontend/                                  # Next.js App Router Web Application
│   ├── public/                                # Static assets
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx                     # Root layout with AuthProvider & Navbar
│   │   │   ├── page.tsx                       # Public Landing Page & Lifecycle Visualizer
│   │   │   ├── globals.css                    # Tailwind CSS + Glassmorphism design tokens
│   │   │   ├── login/page.tsx                 # Firebase & Demo Authentication
│   │   │   ├── signup/page.tsx                # Account registration
│   │   │   ├── chat/page.tsx                  # Main chat platform with SSE streaming
│   │   │   ├── memories/page.tsx              # Memory Explorer & Lifecycle Visualizer
│   │   │   ├── settings/page.tsx              # User preferences, data export, account deletion
│   │   │   └── admin/page.tsx                 # Admin telemetry, users, RL experiments, audit logs
│   │   ├── components/
│   │   │   └── Navbar.tsx                     # Responsive navigation with live API health probe
│   │   └── lib/
│   │       ├── api.ts                         # Typed REST & SSE client
│   │       ├── firebase.ts                    # Firebase Client SDK
│   │       └── auth-context.tsx               # Stateful authentication context
│   ├── package.json                           # Next.js & React dependencies
│   ├── tsconfig.json                          # TypeScript configuration
│   ├── next.config.ts                         # Next.js configuration
│   ├── tailwind.config.ts                     # Tailwind CSS design system
│   ├── postcss.config.mjs                     # PostCSS configuration
│   └── .env.example                           # Frontend client environment template
├── dashboard.py                               # Preserved Streamlit developer research UI
├── run.py                                     # Unified CLI launcher
├── render.yaml                                # Render Infrastructure Blueprint
├── .gitignore                                 # Git exclusion rules
├── .env.example                               # Root environment template
└── README.md                                  # Complete documentation
```

---

## 3. Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS, Lucide Icons |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, NumPy |
| **AI & Inference** | Google Gen AI SDK (`google-genai`), Gemini 2.5 Flash |
| **Semantic Vectors**| Qdrant Vector Database, FastEmbed ONNX (`BAAI/bge-small-en-v1.5`) |
| **Authentication** | Firebase Authentication (Client SDK) + Firebase Admin SDK (Server verification) |
| **Persistence** | SQLite with WAL mode (Local dev) / PostgreSQL connection URL support (Production) |
| **RL Optimization**| LinUCB Contextual Bandit with safety-action masking |
| **Deployment** | Render Blueprint (`render.yaml`) |

---

## 4. Empirical Evaluation Benchmark

The platform includes a reproducible 4-way empirical benchmark comparing memory strategies on a standardized corpus of 100 items (pinned preferences, frequent facts, ephemeral logs, redundant instructions):

```
===============================================================================================
EXPERIMENTAL EVALUATION RESULTS: 4-WAY COMPARATIVE BENCHMARK
===============================================================================================
Strategy                            | Active  | Tokens  | Crit Ret  | Retr Succ  | Saved   | Violations  | Latency 
-----------------------------------------------------------------------------------------------
Baseline (Retain All)               | 100     | 2162    | 100.0%    | 80.0%      | 0.0%    | 0           | 2773.01ms
Recency-Only (LRU)                  | 40      | 898     | 100.0%    | 60.0%      | 60.0%   | 0           | 5945.03ms
Intelligent Forgetting (Proposed)   | 13      | 246     | 100.0%    | 80.0%      | 87.0%   | 0           | 5870.59ms
Reinforcement Learning (LinUCB)     | 50      | 1132    | 100.0%    | 80.0%      | 50.0%   | 0           | 9059.11ms
===============================================================================================
```

### Key Findings
1. **Context Window Compression**: Intelligent Forgetting achieved an **88.6% reduction in active context tokens** (from 2,162 down to 246 tokens).
2. **Critical Knowledge Protection**: **100% of pinned and critical memories** were retained across all runs.
3. **Retrieval Precision**: Matched or outperformed baseline retrieval accuracy while eliminating 87% of working memory clutter.

---

## 5. Local Development (Windows PowerShell)

### Prerequisites
- Python 3.11, 3.12, or 3.13 installed
- Node.js 18+ or 20+ installed
- PowerShell (Windows)

### Step 1: Clone Repository
```powershell
git clone https://github.com/p76266342-del/Intelligent-Forgetting-in-Agentic-AI-.git
cd Intelligent-Forgetting-in-Agentic-AI-
```

### Step 2: Set Up Backend Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
.\.venv\Scripts\pip.exe install -r backend\requirements.txt
.\.venv\Scripts\pip.exe install -e backend
```

### Step 3: Install Frontend Dependencies
```powershell
cd frontend
npm.cmd install
cd ..
```

### Step 4: Configure Environment Files
```powershell
# Copy root environment template
Copy-Item .env.example .env

# Copy frontend environment template
Copy-Item frontend\.env.example frontend\.env.local
```

### Step 5: Run Automated Tests
```powershell
.\.venv\Scripts\python.exe run.py test
```
All 33 pytest automated tests will execute and pass.

### Step 6: Start Local Services

Open two separate PowerShell terminal windows:

**Terminal 1 — FastAPI Backend:**
```powershell
.\.venv\Scripts\python.exe run.py api
# Backend running at http://127.0.0.1:8000
# OpenAPI Swagger docs at http://127.0.0.1:8000/docs
```

**Terminal 2 — Next.js Frontend:**
```powershell
.\.venv\Scripts\python.exe run.py frontend
# Frontend running at http://localhost:3000
```

**Optional — Streamlit Research Dashboard:**
```powershell
.\.venv\Scripts\python.exe run.py dashboard
# Streamlit running at http://localhost:8501
```

---

## 6. Environment Variables Reference

### Backend (`.env` or Render Environment)

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `APP_ENV` | Application environment mode | `development` / `production` |
| `API_HOST` | FastAPI host bind address | `127.0.0.1` (`0.0.0.0` on Render) |
| `API_PORT` | FastAPI port | `8000` |
| `DATABASE_PATH` | SQLite database file location | `data/memories.db` |
| `DATABASE_URL` | Optional PostgreSQL / SQLite database connection URL | `sqlite:///data/memories.db` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `GEMINI_API_KEY` | Google Gemini API key | *(Secret provided in Render/local env)* |
| `GEMINI_MODEL` | Google Gemini model identifier | `gemini-2.5-flash` |
| `QDRANT_URL` | Qdrant vector database URL | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant Cloud API key | *(Optional if local)* |
| `QDRANT_COLLECTION_NAME`| Collection name in Qdrant | `intelligent_forgetting_memories` |
| `EMBEDDING_PROVIDER` | Embedding engine | `fastembed` |
| `EMBEDDING_MODEL` | FastEmbed model identifier | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_DIMENSIONS` | Vector dimensions | `384` |
| `FIREBASE_PROJECT_ID` | Firebase project identifier | `intelligent-forgetting` |
| `FIREBASE_AUTH_DOMAIN` | Firebase authentication domain | `intelligent-forgetting.firebaseapp.com` |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to Firebase Admin service account JSON | `credentials/firebase-service-account.json` |

### Frontend (`frontend/.env.local` or Render Environment)

| Variable | Description | Example |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of deployed FastAPI backend | `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase Web Client API key | `AIzaSy...` |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Authentication domain | `intelligent-forgetting.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase Project ID | `intelligent-forgetting` |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase Web App ID | `1:1234567890:web:abcdef` |

> **Security Note:** In Next.js, only variables prefixed with `NEXT_PUBLIC_` are delivered to the browser. Server credentials (Gemini API keys, Qdrant API keys, database URLs, and Firebase Service Accounts) must **NEVER** be assigned `NEXT_PUBLIC_` prefixes.

---

## 7. Render Deployment Guide

The repository includes a root-level `render.yaml` Blueprint configuring both the FastAPI Python Web Service and the Next.js Node Web Service.

### Deployment Steps:
1. Push your code to your GitHub repository.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New** &rarr; **Blueprint**.
3. Connect your repository: `https://github.com/p76266342-del/Intelligent-Forgetting-in-Agentic-AI-.git`.
4. Render automatically parses `render.yaml` and defines:
   - `intelligent-forgetting-backend` (Python Web Service)
   - `intelligent-forgetting-frontend` (Node.js Web Service)
5. Fill in the required secret environment variables under each service in the Render Dashboard:
   - `GEMINI_API_KEY`
   - `QDRANT_API_KEY` (if using Qdrant Cloud)
   - `NEXT_PUBLIC_FIREBASE_API_KEY`
6. Click **Apply Blueprint**. Render builds and deploys both services automatically.

### Database Persistence & Paid Plan Considerations
- **Local Development**: Fully functional with zero cost using thread-safe SQLite with WAL mode.
- **Render Free Web Services**: Render's free tier containers have an ephemeral filesystem. If the container restarts or re-deploys, local SQLite files reset unless a persistent disk or managed database is attached.
- **Production Long-Term Storage**:
  - **Option A (Render PostgreSQL)**: Provision a Render Managed PostgreSQL database and set `DATABASE_URL=postgresql://...`.
  - **Option B (Render Persistent Disk)**: Attach a persistent disk mount to `/var/data` on a Render Starter plan or above and point `DATABASE_PATH=/var/data/memories.db`.

---

## 8. Security & Multi-Tenant Model

1. **Cryptographic Token Verification**: All requests to protected endpoints verify the Firebase ID token cryptographically via the Firebase Admin SDK.
2. **Strict Server-Derived UID**: The backend derives `user.uid` exclusively from the verified token. Client-provided user IDs in payloads or URLs are never trusted.
3. **Mandatory Vector Payload Filters**: Every semantic search executed against Qdrant automatically injects an `owner_uid == user.uid` condition. Cross-tenant vector leakage is mechanically impossible.
4. **GDPR Account Deletion**: When an account is deleted, the backend performs a clean cascade across SQLite records (`users`, `conversations`, `messages`, `memories`) and issues vector point purges in Qdrant.
5. **Role-Based Access Control (RBAC)**: Administrative endpoints require verified custom claims (`is_admin == True` or `role == "admin"`). Regular users receive immediate `403 Forbidden` responses.

---

## 9. Known Limitations

1. **Qdrant Local In-Memory Fallback**: If `QDRANT_URL` is unreachable, the vector service transparently switches to an in-memory client (`:memory:`). Vector records in memory reset when the backend process restarts unless connected to a live Qdrant server or Qdrant Cloud.
2. **Gemini Demo Simulation Mode**: When `GEMINI_API_KEY` is not configured, the service falls back to a deterministic conversational responder that accurately tests memory recall, token streaming, and candidate memory extraction without incurring API costs.
3. **SSE Streaming Buffering**: Some enterprise reverse proxies buffer HTTP responses; Server-Sent Events (SSE) include `X-Accel-Buffering: no` headers where supported.

---

## 10. License

MIT License &bull; Intelligent Forgetting in Agentic AI Project
