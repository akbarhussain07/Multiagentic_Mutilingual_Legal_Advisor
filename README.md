# Legal Advisor

Legal Advisor is a full-stack, AI-assisted legal information platform focused on Pakistani property law, Islamic property law, and property-case procedure. It combines a React interface with a Django REST API and a retrieval-augmented generation (RAG) pipeline that answers questions from indexed legal sources and returns supporting references.

> [!IMPORTANT]
> Legal Advisor provides source-based educational information. It is not a substitute for advice from a qualified Pakistani lawyer or Islamic scholar.

## Features

- Separate Pakistani and Islamic legal views, plus a Both mode for cross-domain questions
- Source-grounded answers with citations and practical next steps
- Multi-agent question routing using LangGraph
- Semantic answer memory for repeated, materially equivalent questions
- Token-based signup, login, and authenticated chat
- Persistent chat sessions and message history
- User profiles, password reset, and application ratings
- Admin dashboard for user management and Markdown document ingestion
- Background ingestion with upload progress tracking
- Responsive React interface

## Screenshots

### Home page

![Legal Advisor home page](pics/HomePage.png)

### Features

![Legal Advisor features](pics/features.png)

### Sign up

![Legal Advisor signup page](pics/SignupPage.png)

### Chat

![Legal Advisor chat page](pics/ChatPage.png)

### Referenced answer

![Chat answer with legal references](pics/ChatWithReference.png)

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, React Router, Vite, Lucide React |
| Backend | Python, Django 6, Django REST Framework |
| Authentication | Django token authentication |
| Application database | PostgreSQL |
| RAG orchestration | LangChain and LangGraph |
| LLM | Groq `llama-3.3-70b-versatile` |
| Embeddings | `BAAI/bge-m3` dense + BM25 sparse |
| Vector database | Qdrant (`legal-advisor`, RRF hybrid) |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Answer memory | SQLite payloads + Qdrant vectors |

## Project Structure

```text
LegalAdvisor/
├── backend/
│   ├── accounts/          # Authentication and profile endpoints
│   ├── backend/           # Django project configuration
│   ├── data/              # Legal Markdown sources and ingestion state
│   ├── legal_admin/       # Admin user-management API
│   ├── rag_api/           # RAG, chat history, ratings, and ingestion
│   ├── scripts/           # Legacy/import utilities
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # Landing-page components
│   │   └── Pages/         # Application pages and API client
│   └── package.json
├── pics/                  # README screenshots
└── README.md
```

## Prerequisites

- Python 3.12 or newer
- Node.js 20.19+ (or 22.12+)
- PostgreSQL
- A Groq API key
- A running Qdrant instance (`http://localhost:6333` by default)

The first ingest downloads `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3`, which requires additional time and disk space.

## Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd LegalAdvisor
```

### 2. Create the PostgreSQL database

Create a PostgreSQL database and user for the application. The current Django database settings are in `backend/backend/settings.py`; update them for your local PostgreSQL instance before running migrations.

For production or shared development, move the database credentials and Django secret key to environment variables rather than committing them to source control.

### 3. Configure the backend

From the project root:

```bash
python -m venv legalenv
```

Activate the environment:

```bash
# Windows PowerShell
.\legalenv\Scripts\Activate.ps1

# macOS/Linux
source legalenv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

Create `backend/.env`:

```dotenv
GROQ_API_KEY=your_groq_api_key
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal-advisor

# Optional email configuration for password resets
EMAIL_HOST_USER=your_email_address
EMAIL_HOST_PASSWORD=your_email_app_password

# Optional overrides
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu
RETRIEVAL_TOP_K=40
RERANK_TOP_K=15
MAX_CHUNKS_PER_DOC=3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_MAX_LENGTH=1024
INGESTION_VERSION=legal-ingestion-v2
```

Apply migrations and optionally create an administrator:

```bash
cd backend
python manage.py migrate
python manage.py createsuperuser
```

### 4. Index the legal sources

Legal source files are stored as Markdown or PDF under:

- `backend/data/pakistani/` (Pakistani law; `legal_system=Pakistani`)
- `backend/data/islamic/` (Islamic law; `legal_system=Islamic`)
- `backend/data/procedure/` (Pakistani procedure/case material; still `legal_system=Pakistani`)

From `backend/`, ingest all datasets into Qdrant (required after this migration; old E5/Pinecone vectors are incompatible):

```bash
python -m rag_api.ingestion_service --dataset all --clear-first
```

Useful ingestion options:

```bash
# Validate chunking without uploading vectors
python -m rag_api.ingestion_service --dataset all --dry-run

# Reprocess unchanged documents
python -m rag_api.ingestion_service --dataset all --force

# Process one collection
python -m rag_api.ingestion_service --dataset pakistani
```

The Qdrant collection uses cosine dense vectors (1024-d bge-m3) plus BM25 sparse vectors fused with RRF. The ingestion command creates the collection if it is missing.

Old Pinecone/E5 vectors must not be mixed with the new index. Always re-ingest after switching.

### 5. Start the backend

From `backend/`:

```bash
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000`.

Check its status at:

```text
http://127.0.0.1:8000/api/health/
```

### 6. Configure and start the frontend

In a second terminal:

```bash
cd frontend
npm install
```

The frontend uses `http://127.0.0.1:8000` by default. To use another backend, create `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Start Vite:

```bash
npm run dev
```

Open `http://localhost:5173`.

## Common Commands

### Frontend

```bash
cd frontend
npm run dev       # Start the development server
npm run build     # Create a production build
npm run lint      # Run ESLint
npm run preview   # Preview the production build
```

### Backend

```bash
cd backend
python manage.py runserver
python manage.py test
python manage.py makemigrations
python manage.py migrate
```

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/accounts/signup/` | Create an account |
| `POST` | `/accounts/login/` | Log in and receive an auth token |
| `POST` | `/accounts/password-reset/` | Request a password-reset email |
| `PATCH` | `/accounts/password-reset-confirm/` | Set a new password |
| `POST` | `/api/query/` | Ask an authenticated legal question |
| `GET` | `/api/history/` | List the current user's chats |
| `GET` | `/api/history/<session_id>/` | Read a chat |
| `DELETE` | `/api/history/<session_id>/delete/` | Delete a chat |
| `GET` | `/api/health/` | Check API and RAG configuration |
| `POST` | `/api/rate-app/` | Submit a 1–5 rating |
| `POST` | `/api/upload-doc/` | Upload and index an authenticated Markdown or PDF file |
| `GET` | `/api/upload-status/<task_id>/` | Poll an ingestion task |
| `GET` | `/admin/users/` | List users as an administrator |

Authenticated requests use:

```http
Authorization: Token <token>
```

## How the RAG Pipeline Works

1. Greetings and small talk are answered directly. They never hit Qdrant.
2. The master agent normalizes the question, considers recent chat context, and checks semantic answer memory.
3. It routes to the Pakistani agent, the Islamic agent, or both. There is no Procedure agent; Pakistani procedure is handled by the Pakistani agent.
4. Each selected agent runs hybrid search (bge-m3 + BM25 + RRF, top 40) with a `legal_system` metadata filter. Language is stored but never used as a retrieval filter.
5. Candidates are reranked with `bge-reranker-v2-m3` (top 15) and capped at 3 chunks per document.
6. The Groq answer generator produces a direct answer, analysis, practical steps, missing information, and citations.
7. Chat history is stored in PostgreSQL; eligible answers may also be reused through Qdrant/SQLite semantic memory.

## Adding Legal Sources

Add a `.md`, `.markdown`, or `.pdf` file to the appropriate directory under `backend/data/`, then run the ingestion command for that dataset. Front matter, titles, and sections are stored as Qdrant payload metadata.

Administrators can also upload Markdown or PDF documents through the dashboard. Uploaded documents are indexed in a background thread, and the frontend polls the task-status endpoint until processing completes.

## Security Notes

- Do not commit `.env` files, API keys, email app passwords, database passwords, or Django secret keys.
- Replace development settings such as `DEBUG=True`, permissive hosts, and unrestricted CORS before deployment.
- Restrict authenticated profile-management endpoints and verify object ownership before exposing the service publicly.
- Use a persistent task queue and shared cache instead of background threads and local-memory status tracking in a multi-process production deployment.

## Disclaimer

The answers generated by this project are for education and general guidance only. Laws and interpretations can change, and individual facts materially affect legal outcomes. Always consult a qualified lawyer or scholar before acting on legal information.

## Team

- Aftab Ali
- Akbar Hussain
- Siraj Ahmed
