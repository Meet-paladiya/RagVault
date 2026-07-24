# AI Knowledge Hub

> **100% Offline** · Self-Hosted · RAG-Powered AI Learning System

A fully offline, self-hosted Retrieval-Augmented Generation (RAG) learning platform for students. Upload PPTX, PDF, video, and audio files to create "knowledge spaces," then ask questions, generate quizzes, track weak topics, and get personalized study recommendations — all powered by local AI models with zero internet connectivity required after setup.

---

## ⚡ Quick Start

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker | 24.0+ | |
| Docker Compose | 2.20+ | |
| RAM | 16GB minimum | 8GB minimum free for model inference |
| Disk | 30GB free | For models + data |

### 1. Clone & Configure

```bash
git clone <repo-url> ai-knowledge-hub
cd ai-knowledge-hub
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

This starts 5 services: `postgres`, `chromadb`, `ollama`, `backend`, `frontend`.

### 3. One-Time Model Downloads

> ⚠️ **Internet required only during this step.** After this, the system runs fully offline.

**Download the LLM (choose one):**
```bash
# Default — Qwen 2.5 7B (recommended, ~4.7GB)
docker exec hub_ollama ollama pull qwen2.5:7b-instruct

# Alternatives:
# docker exec hub_ollama ollama pull llama3.1:8b
# docker exec hub_ollama ollama pull mistral:7b
# docker exec hub_ollama ollama pull phi4
# docker exec hub_ollama ollama pull gemma3
```

**Embedding & Whisper models** are downloaded automatically by the backend on first startup (stored in the `hf_cache` Docker volume). This takes 2–5 minutes on first run.

### 4. Open the App

```
http://localhost:3000
```

Register an account, create a Knowledge Space, upload documents, and start learning!

---

## 🌐 No Internet Required After Setup

Once all models are downloaded, the system operates **100% offline**:

- ❌ No Gemini / OpenAI / Anthropic API calls
- ❌ No cloud embeddings
- ❌ No cloud speech-to-text
- ❌ No cloud storage
- ✅ All inference runs locally via Ollama + SentenceTransformers + Faster-Whisper
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
   │    └── PPTX/PDF/Video/Audio → Parse → Chunk → Embed → ChromaDB
   ├── RAG Service (LangGraph)
   │    └── Question → Embed → Retrieve → LLM → Answer + Citations
   ├── Quiz Service
   │    └── LLM generates MCQs → grade → weak topics
   └── Recommendation Service
        └── LangGraph → LLM study plan
   │
   ├── PostgreSQL (users, chats, messages, documents, quizzes)
   ├── ChromaDB (vector embeddings, per chat_id collection)
   └── Ollama (local LLM: qwen2.5:7b-instruct default)
```

---

## 📁 Supported File Types

| Type | Extensions | Processing |
|------|-----------|------------|
| PDF | `.pdf` | PyMuPDF (page-by-page) |
| PowerPoint | `.pptx` | python-pptx (slide-by-slide) |
| Video | `.mp4 .mkv .mov .avi .webm` | ffmpeg audio extract → Faster-Whisper |
| Audio | `.mp3 .wav .m4a .ogg .flac .aac` | Faster-Whisper |

> ❌ DOCX, images, and any other file types are rejected with a clear error message.

---

## 🖥 Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui |
| State | TanStack Query + Zustand |
| Backend | FastAPI + LangGraph + LangChain |
| Local LLM | Ollama (GGUF-quantized models) |
| Embeddings | SentenceTransformers `BAAI/bge-base-en-v1.5` |
| Vector DB | ChromaDB (persistent local) |
| Relational DB | PostgreSQL 16 |
| Speech-to-Text | Faster-Whisper (local, `base` model) |
| Auth | JWT (access + refresh tokens), bcrypt |
| Deployment | Docker + Docker Compose |

No deviations from the specified stack were made.

---

## ⚙️ Configuration

All configuration is in `.env`. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | LLM to use for generation |
| `EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | Embedding model |
| `WHISPER_MODEL` | `base` | Whisper model size (tiny/base/small/medium/large-v3) |
| `CHUNK_SIZE` | `600` | Target tokens per chunk |
| `CHUNK_OVERLAP` | `100` | Token overlap between chunks |
| `TOP_K` | `5` | Number of chunks to retrieve per query |
| `WHISPER_DEVICE` | `cpu` | Set to `cuda` if GPU available |

---

## 🎮 GPU Acceleration (Optional)

For significantly faster inference, uncomment the GPU section in `docker-compose.yml`:

```yaml
# In the ollama service:
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

## 🚀 Usage Guide

### Creating a Knowledge Space

1. Click **"+ New Chat"** in the sidebar
2. Give it a name (e.g., "Machine Learning Finals")
3. Upload your documents via drag-and-drop or click to browse

### Chatting with Your Documents

- Type questions in the chat input and press **Enter** or **Ctrl+Enter**
- Answers stream in real-time with source citations showing filename and page number
- Citations are grounded in your documents — the LLM cannot invent sources

### Generating a Quiz

1. Open the **Quiz** tab in the right panel
2. Enter a topic (e.g., "neural networks")
3. Click **Generate Quiz** — the LLM creates MCQs from relevant document chunks
4. Submit answers to see your score and weak topics
5. Click **Get Recommendations** for a personalized study plan

### Adding More Documents

Upload new documents to an existing chat — they **accumulate** in the knowledge base (default behavior). Use **"Clear Knowledge"** (red button) to wipe all vectors and start fresh.

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
docker compose logs -f ollama

# Restart a service
docker compose restart backend

# Full teardown (preserves data volumes)
docker compose down

# Full teardown + delete all data
docker compose down -v
```

---

## 📊 API Reference

The API is documented at `http://localhost:8000/docs` (Swagger UI) after startup.

**Core endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register new user |
| `POST` | `/auth/login` | Login, get JWT tokens |
| `GET` | `/chats` | List all knowledge spaces |
| `POST` | `/chats` | Create new knowledge space |
| `POST` | `/chats/{id}/documents` | Upload + ingest document |
| `POST` | `/chats/{id}/messages` | Ask a question (SSE streaming) |
| `GET` | `/chats/{id}/messages` | Get chat history |
| `POST` | `/chats/{id}/quiz` | Generate quiz |
| `POST` | `/quiz/{id}/submit` | Submit quiz answers |
| `GET` | `/chats/{id}/recommendations` | Get study recommendations |
| `POST` | `/chats/{id}/clear-knowledge` | Wipe all vectors for chat |

---

## 🗂 Project Structure

```
ai-knowledge-hub/
├── frontend/           # React + Vite + TypeScript
│   ├── src/
│   │   ├── api/        # TanStack Query hooks
│   │   ├── components/ # UI components
│   │   ├── pages/      # Route pages
│   │   ├── store/      # Zustand stores
│   │   └── types/      # TypeScript types
│   └── Dockerfile
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── models/     # SQLAlchemy ORM
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── routers/    # FastAPI routers
│   │   ├── services/   # Business logic
│   │   ├── utils/      # Parsers, chunker, embedder
│   │   └── core/       # Auth, security, dependencies
│   ├── alembic/        # DB migrations
│   └── Dockerfile
├── docker/             # Nginx config
├── docs/               # Documentation
├── docker-compose.yml  # All services
└── .env.example        # Config template
```

---

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.

---

> **Note to contributors:** This system is intentionally 100% offline. Please do not add any cloud API calls, external service dependencies, or internet-required features. All AI capabilities must use locally-running models.
