# RagVault

> **100% Offline** · Self-Hosted · RAG-Powered AI Learning System

A fully offline, self-hosted Retrieval-Augmented Generation (RAG) learning platform for students. Upload PDF, PPTX, Word, video, and audio files to create "knowledge spaces," then ask questions, generate quizzes, create AI study notes, track weak topics, and get personalized study recommendations — all powered by local AI models with zero internet connectivity required after setup.

---

## ⚡ Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker | 24.0+ | |
| Docker Compose | 2.20+ | |
| RAM | 16GB minimum | 8GB minimum free for model inference |
| Disk | 5GB free | For model + data (model is ~1.06 GB) |

### 1. Clone & Configure

```bash
git clone https://github.com/Meet-paladiya/RagVault.git
cd RagVault
cp .env.example .env
```

Edit `.env` with at minimum:
```bash
POSTGRES_PASSWORD=your_strong_password
JWT_SECRET=your_random_32_char_secret_here
```

### 2. Start All Services

```bash
docker compose up -d
```

This starts **6 services**: `model-init`, `postgres`, `chromadb`, `llm`, `backend`, `frontend`.

> ℹ️ `model-init` automatically downloads the GGUF model on first startup. The `llm` service waits for it to finish before starting.

### 3. Open the App

```
http://localhost:3000
```

Register an account, create a Knowledge Space, upload documents, and start learning!

> ⚠️ **Internet is only required during the very first `docker compose up -d`** — to pull Docker images and download the LLM model (~1.06 GB). After that, the entire system runs **100% offline**.

---

## 🌐 No Internet Required After Setup

Once all services have started and the model is downloaded, the system operates **100% offline**:

- ❌ No Gemini / OpenAI / Anthropic API calls
- ❌ No cloud embeddings
- ❌ No cloud speech-to-text
- ❌ No cloud storage
- ✅ All inference runs locally via **llama.cpp** + **FastEmbed (ONNX)** + **Faster-Whisper**
- ✅ All data stored locally in PostgreSQL + ChromaDB

---

## 🏗 Architecture

```
Browser (React + Vite)
   │  REST + SSE  │
   ▼               ▼
FastAPI Backend (port 8000)
   ├── Auth (JWT)
   ├── Ingestion Service
   │    └── PDF/PPTX/Word/TXT/MD/Image/Video/Audio → Parse → Chunk → Embed → ChromaDB
   ├── RAG Service (LangGraph)
   │    └── Question → Embed → Retrieve → LLM → Answer + Citations  (SSE streaming)
   ├── Quiz Service
   │    └── LLM generates MCQs in parallel batches → grade → weak topics
   ├── Notes Service
   │    └── LLM generates page-by-page study cards → downloadable PDF
   └── Recommendation Service
        └── LangGraph → LLM → personalised Markdown study plan
   │
   ├── PostgreSQL (users, chats, messages, documents, quizzes, notes)
   ├── ChromaDB 0.5.18 (vector embeddings, per chat_id collection)
   └── llama.cpp Server (port 8080 → local Qwen2.5-1.5B-Instruct GGUF)
```

### Model Auto-Download

A dedicated `model-init` container (`python:3.11-alpine`) runs `scripts/setup_model.py` at first startup. It downloads `qwen2.5-1.5b-instruct-q4_k_m.gguf` (~1.06 GB) from HuggingFace into the `./models/` directory with automatic resume-and-retry on failure. The `llm` service only starts once this completes successfully.

---

## 📁 Supported File Types

| Type | Extensions | Processing |
|------|-----------|------------|
| PDF | `.pdf` | PyMuPDF (page-by-page) + Tesseract OCR for scanned/image pages |
| PowerPoint | `.pptx` `.ppt` | python-pptx (slide-by-slide); binary `.ppt` fallback via raw stream extraction |
| Word | `.docx` `.doc` | python-docx; ZIP/XML fallback |
| Plain Text | `.txt` `.md` | Direct read, split into ~2000-char pseudo-pages |
| Image | `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tiff` | Tesseract OCR with contrast enhancement |
| Video | `.mp4` `.mkv` `.mov` `.avi` `.webm` | ffmpeg audio extract → Faster-Whisper |
| Audio | `.mp3` `.wav` `.m4a` `.ogg` `.flac` `.aac` | Faster-Whisper (PyAV fallback) |

> ❌ Any other file type is rejected with a clear 422 error message.
> 📦 Maximum upload size: **2 GB** per file.

---

## 🖥 Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui |
| Animations | Framer Motion + Three.js |
| State | TanStack Query v5 + Zustand v5 |
| Backend | FastAPI + LangGraph + LangChain Community |
| Local LLM | **llama.cpp server** (`ghcr.io/abetlen/llama-cpp-python`) — OpenAI-compatible API |
| Default Model | `qwen2.5-1.5b-instruct-q4_k_m.gguf` (~1.06 GB, auto-downloaded) |
| Embeddings | **FastEmbed** (ONNX Runtime) — `BAAI/bge-small-en-v1.5` |
| Vector DB | ChromaDB 0.5.18 (persistent local) |
| Relational DB | PostgreSQL 16 |
| Speech-to-Text | Faster-Whisper (local, `base` model) |
| OCR | Tesseract OCR (via `pytesseract` + `PyMuPDF`) |
| Auth | JWT (access + refresh tokens), bcrypt |
| Deployment | Docker + Docker Compose |

No deviations from the specified stack were made.

---

## ⚙️ Configuration

All configuration is in `.env`. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `qwen2.5-1.5b-instruct` | Model identifier sent to the llama.cpp server |
| `LLM_BASE_URL` | `http://llm:8000/v1` | OpenAI-compatible base URL for the llama.cpp server |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Used by recommendation & notes services via LangChain Ollama integration |
| `OLLAMA_BASE_URL` | `http://llm:8080/v1` | Ollama-compatible URL (points to llama.cpp server) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed ONNX embedding model |
| `WHISPER_MODEL` | `base` | Whisper model size (tiny/base/small/medium/large-v3) |
| `CHUNK_SIZE` | `600` | Target tokens per chunk |
| `CHUNK_OVERLAP` | `100` | Token overlap between chunks |
| `TOP_K` | `5` | Number of chunks to retrieve per query |
| `WHISPER_DEVICE` | `cpu` | Set to `cuda` if GPU available |
| `POSTGRES_PASSWORD` | *(must set)* | PostgreSQL password |
| `JWT_SECRET` | *(must set)* | Random 32+ char string for JWT signing |

---

## 🚀 Usage Guide

### Creating a Knowledge Space

1. Click **"+ New Chat"** in the sidebar
2. Give it a name (e.g., "Machine Learning Finals")
3. Upload your documents via drag-and-drop or click to browse

### Chatting with Your Documents

- Type questions in the chat input and press **Enter** or **Ctrl+Enter**
- Answers stream token-by-token in real time via SSE with source citations (filename + page number)
- Citations are strictly grounded — the LLM cannot invent sources

### Generating a Quiz

1. Open the **Quiz** tab in the right panel
2. Enter a topic (e.g., "neural networks") and choose number of questions
3. Click **Generate Quiz** — the LLM creates MCQs from relevant document chunks in parallel batches
4. Submit answers to see your score, explanations, and weak topics
5. Click **Get Recommendations** for a personalized Markdown study plan based on your last 5 quiz results

### AI Notes

1. Open the **Notes** tab in the right panel
2. Click **Generate Notes** — the LLM creates structured page-by-page study cards for all uploaded documents
3. Download as a **searchable PDF** via the PDF download button
4. After submitting a quiz, generate **Remedial Notes** targeting only the concepts you got wrong (also downloadable as PDF)

### Adding More Documents

Upload new documents to an existing chat — they accumulate in the knowledge base. Use **"Clear Knowledge"** to wipe all vectors and start fresh without deleting the chat.

### Renaming or Deleting a Knowledge Space

- Chats auto-title themselves after the first question using the LLM
- Rename via the PATCH chat endpoint or from the UI
- Delete a chat (purges messages, documents, quizzes, notes, and vector collection)

---

## 🛠 Development Setup

```bash
# Backend (Python 3.11)
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (Node 20)
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:8000`, frontend on `http://localhost:3000` (with proxy to backend).

---

## 🧪 Running Tests

```bash
# Backend tests
cd backend
pytest tests/ -v --tb=short

# Frontend lint
cd frontend
npm run lint
```

---

## 🔧 Service Management

```bash
# View logs
docker compose logs -f backend
docker compose logs -f llm

# Restart a service
docker compose restart backend

# Full teardown (preserves data volumes)
docker compose down

# Full teardown + delete all data
docker compose down -v
```

### Optional: Nginx Reverse Proxy

An Nginx service is defined in `docker-compose.yml` but gated behind a Docker Compose profile. To enable it:

```bash
docker compose --profile nginx up -d
```

Nginx will serve on port 80 and proxy to both backend and frontend.

---

## 📊 API Reference

The API is documented at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` after startup.

**Core endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register new user |
| `POST` | `/auth/login` | Login, get JWT tokens |
| `GET` | `/chats` | List all knowledge spaces |
| `POST` | `/chats` | Create new knowledge space |
| `GET` | `/chats/{id}` | Get a single knowledge space |
| `PATCH` | `/chats/{id}` | Rename a knowledge space |
| `DELETE` | `/chats/{id}` | Delete a knowledge space (purges all data) |
| `POST` | `/chats/{id}/documents` | Upload + ingest document (async, returns 202) |
| `GET` | `/chats/{id}/documents` | List documents and their processing status |
| `DELETE` | `/chats/{id}/documents/{doc_id}` | Delete a single document and its vectors |
| `POST` | `/chats/{id}/messages` | Ask a question (SSE streaming or JSON) |
| `GET` | `/chats/{id}/messages` | Get chat history |
| `DELETE` | `/chats/{id}/messages` | Clear all messages |
| `DELETE` | `/chats/{id}/messages/{msg_id}` | Delete a single message |
| `POST` | `/chats/{id}/quiz` | Generate quiz (MCQs from documents) |
| `GET` | `/chats/{id}/quiz-history` | List all past quizzes for a space |
| `POST` | `/quiz/{id}/submit` | Submit quiz answers, get score + weak topics |
| `GET` | `/chats/{id}/recommendations` | Get personalized study plan (LangGraph) |
| `POST` | `/chats/{id}/notes` | Generate AI study note cards |
| `GET` | `/chats/{id}/notes` | Fetch latest AI notes |
| `GET` | `/chats/{id}/notes/pdf` | Download AI notes as PDF |
| `POST` | `/chats/{id}/quiz-remedial-notes` | Generate remedial notes for missed questions |
| `GET` | `/chats/{id}/quiz-remedial-notes` | Fetch latest remedial notes |
| `GET` | `/chats/{id}/quiz-remedial-notes/pdf` | Download remedial notes as PDF |
| `POST` | `/chats/{id}/clear-knowledge` | Wipe all vectors + documents for a chat |
| `GET` | `/health` | Health check (`{"status": "ok"}`) |

---

## 🗂 Project Structure

```
RagVault/
├── frontend/               # React + Vite + TypeScript
│   ├── src/
│   │   ├── api/            # TanStack Query hooks
│   │   ├── components/     # UI components (shadcn/ui + custom)
│   │   ├── pages/          # Route pages
│   │   ├── store/          # Zustand stores
│   │   ├── types/          # TypeScript types
│   │   └── theme.ts        # Design system tokens
│   ├── nginx.conf          # Production Nginx config for the frontend container
│   └── Dockerfile
├── backend/                # FastAPI application
│   ├── app/
│   │   ├── models/         # SQLAlchemy ORM (user, chat, document, message, quiz, note, memory)
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── routers/        # FastAPI routers (auth, chats, documents, messages, quiz, notes)
│   │   ├── services/       # Business logic (rag, quiz, notes, ingestion, recommendation, auth)
│   │   ├── utils/          # Parsers, chunker, FastEmbed embedder, ChromaDB client
│   │   └── core/           # Auth dependencies, security
│   ├── alembic/            # DB migrations
│   └── Dockerfile          # python:3.11-slim + Tesseract + ffmpeg
├── models/                 # GGUF model directory (auto-populated by model-init)
├── scripts/
│   └── setup_model.py      # Auto-download script for qwen2.5-1.5b-instruct-q4_k_m.gguf
├── docker/
│   └── nginx.conf          # Nginx reverse proxy config (optional profile)
├── docker-compose.yml      # All 6 services
└── .env.example            # Config template
```

---

## 🎮 GPU Acceleration (Optional)

For faster inference, add GPU resources to the `llm` service in `docker-compose.yml`:

```yaml
# In the llm service:
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

**Requirements:** NVIDIA GPU + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed on host.

Also set in `.env`:
```bash
WHISPER_DEVICE=cuda
```

---

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.

---

> **Note to contributors:** This system is intentionally 100% offline. Please do not add any cloud API calls, external service dependencies, or internet-required features. All AI capabilities must use locally-running models.
