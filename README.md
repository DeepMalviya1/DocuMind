# DocuMind

**DocuMind** is an AI-powered document question-answering system. Upload any file — PDF, Word, Excel, PowerPoint, images, CSV, SQLite databases, and more — then ask questions about the content in plain English. Powered by Groq LLMs with RAG (Retrieval-Augmented Generation), real-time streaming, per-user isolated knowledge bases, and a full metrics dashboard.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green.svg)](https://fastapi.tiangolo.com/)
[![FAISS](https://img.shields.io/badge/FAISS-Vector%20Search-orange.svg)](https://github.com/facebookresearch/faiss)
[![Groq](https://img.shields.io/badge/Groq-LLM-purple.svg)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Screenshots

> Place your screenshots in `assets/screenshots/` — they will appear here automatically.

| Upload Documents | Ask a Question |
|:-:|:-:|
| ![Upload](assets/screenshots/upload.png) | ![Ask](assets/screenshots/ask.png) |

| Streaming Response | Swagger API Docs |
|:-:|:-:|
| ![Stream](assets/screenshots/stream.png) | ![Swagger](assets/screenshots/swagger.png) |

| Chat History | Metrics Dashboard |
|:-:|:-:|
| ![History](assets/screenshots/history.png) | ![Metrics](assets/screenshots/metrics.png) |

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Server](#running-the-server)
- [API Reference](#api-reference)
- [Usage Walkthrough](#usage-walkthrough)
- [AI Models](#ai-models)
- [Supported File Types](#supported-file-types)
- [Metrics Explained](#metrics-explained)
- [Environment Variables](#environment-variables)
- [Security](#security)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Multi-format document ingestion** — PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, ODT, PNG, JPG, BMP, TIFF, SQLite `.db`
- **Vision-powered image understanding** — images and charts embedded inside documents are automatically described using **Llama 4 Scout** (multimodal vision model)
- **OCR fallback** — scanned/image-only PDF pages are processed with Tesseract OCR so no content is missed
- **RAG pipeline** — documents are chunked, embedded with `all-MiniLM-L6-v2`, and stored in a FAISS vector index for fast semantic retrieval
- **Two user-selectable chat models**:
  - `llama-instant` — Llama 3.1 8B Instant, fastest responses
  - `qwen-qwq` — Qwen 3 32B, deep reasoning for complex analysis
- **Real-time streaming** — Server-Sent Events (SSE) via `POST /stream/ask` for a word-by-word ChatGPT-like experience
- **Per-file knowledge bases** — each uploaded file gets its own isolated vector space and conversation history; query one file or all files together
- **Multi-user authentication** — register, login, and Bearer token auth on all protected endpoints with full user-level data isolation
- **Persistent chat history** — conversation context is preserved per file (last 20 messages fed as history to the LLM)
- **Full metrics logging** — every query logs latency (ms), token usage, relevance score, model used, and answer length
- **Interactive API docs** — full Swagger UI available at `/docs`

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend framework** | FastAPI + Uvicorn |
| **LLM provider** | Groq API |
| **Chat models** | Llama 3.1 8B Instant, Qwen 3 32B |
| **Vision model** | Llama 4 Scout 17B (multimodal) |
| **Embeddings** | `sentence-transformers` — `all-MiniLM-L6-v2` (384-dim) |
| **Vector store** | FAISS `IndexFlatL2` (CPU) |
| **OCR** | Tesseract + Pytesseract |
| **Document parsing** | PyMuPDF, python-docx, python-pptx, pandas, openpyxl, xlrd, odfpy, Pillow |
| **Database** | SQLite (users, tokens, chat history, files, metrics) |
| **Auth** | HTTP Bearer token |
| **Streaming** | Server-Sent Events (SSE) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Client                                │
│           (curl / Swagger UI / your frontend)               │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼─────────────────────────────────────┐
│                   FastAPI  (api.py)                          │
│  /register  /login  /upload  /ask  /stream/ask               │
│  /files     /history  /metrics  /models                      │
└────────┬──────────────────────┬──────────────────────────────┘
         │                      │
   ┌─────▼──────┐         ┌─────▼───────┐
   │  SQLite DB │         │  FAISS      │
   │  users     │         │  Vector     │
   │  tokens    │         │  Store      │
   │  history   │         │  (chunks    │
   │  files     │         │   +index)   │
   │  metrics   │         └─────────────┘
   └────────────┘

RAG Pipeline — Upload:
  File → Loader → Text Extraction → Chunker (500 chars, 100 overlap)
       → Embedder (all-MiniLM-L6-v2) → FAISS Index

RAG Pipeline — Query:
  Question → Embed → FAISS Search (top 5 chunks)
           → Build Prompt (system + history + context)
           → Groq LLM → Answer (blocking or streamed SSE)
```

---

## Project Structure

```
DocuMind/
├── main.py                    # Entry point — loads .env and starts server
├── requirements.txt           # Python dependencies
├── .env                       # Your secrets (do NOT commit)
├── .env.example               # Environment variable template
│
├── scripts/
│   ├── api.py                 # All FastAPI routes and request/response models
│   ├── chat.py                # Blocking Q&A with full metrics capture
│   ├── loader.py              # Document loader for all supported file types
│   ├── models.py              # LLM model registry (chat + vision definitions)
│   ├── processor.py           # Text chunking, embedding, FAISS vector store
│   ├── prompts.py             # System and user prompt templates
│   ├── vision.py              # Groq vision calls (Llama 4 Scout)
│   ├── db.py                  # SQLite helpers (users, tokens, history, metrics)
│   └── log.py                 # Logging configuration
│
├── streaming/
│   ├── api.py                 # Streaming route helpers
│   └── chat.py                # Streaming Q&A (SSE generator)
│
├── docs/                      # Uploaded documents saved here (auto-created)
├── vectorstore/               # FAISS index + chunk metadata (auto-created)
│   ├── faiss.index
│   └── chunks.json
├── database/
│   └── users.db               # SQLite database (auto-created)
├── logs/
│   └── app.log                # Application logs (auto-created)
└── assets/
    └── screenshots/           # Place solution screenshots here
```

---

## Prerequisites

- Python **3.10+**
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
- A [Groq API key](https://console.groq.com/keys) (free tier available)

### Install Tesseract

**Ubuntu / Debian**
```bash
sudo apt install tesseract-ocr
```

**macOS**
```bash
brew install tesseract
```

**Windows**
Download the installer from the [UB-Mannheim Tesseract releases page](https://github.com/UB-Mannheim/tesseract/wiki).

---

## Installation

**1. Clone the repository**
```bash
git clone https://github.com/your-username/documind.git
cd documind
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**
```bash
cp .env.example .env
```

Open `.env` and set your Groq API key:
```
SECRET_KEY=your_groq_api_key_here
```

---

## Running the Server

```bash
uvicorn main:app --reload
```

| URL | Description |
|---|---|
| `http://127.0.0.1:8000` | Base API |
| `http://127.0.0.1:8000/docs` | Interactive Swagger UI |
| `http://127.0.0.1:8000/redoc` | ReDoc documentation |

---

## API Reference

### Authentication

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/register` | Create a new account | No |
| `POST` | `/login` | Login and receive a Bearer token | No |

### Documents

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/upload` | Upload one or more documents | Yes |
| `GET` | `/files` | List all files you have uploaded | Yes |

### Q&A

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/ask` | Ask a question — blocking, full response | Yes |
| `POST` | `/stream/ask` | Ask a question — real-time SSE streaming | Yes |

### History & Metrics

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/history` | Retrieve your chat history | Yes |
| `GET` | `/metrics` | View per-query performance metrics | Yes |
| `GET` | `/models` | List available AI models | No |

---

## Usage Walkthrough

### 1 — Register and login

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
# → {"token": "YOUR_TOKEN", ...}
```

### 2 — Upload a document

```bash
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@report.pdf"
```

Upload multiple files at once:
```bash
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@report.pdf" \
  -F "files=@sales_data.xlsx" \
  -F "files=@slides.pptx"
```

### 3 — Ask a question (blocking)

```bash
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the key findings?", "model": "llama-instant"}'
```

**Response:**
```json
{
  "asked_by": "alice",
  "question": "What are the key findings?",
  "model_used": "llama-3.1-8b-instant",
  "answer": "The key findings are...",
  "sources": ["report.pdf"],
  "latency_ms": 1247.5,
  "input_tokens": 1450,
  "output_tokens": 320,
  "total_tokens": 1770,
  "relevance_score": 0.4821
}
```

### 4 — Ask a question (streaming)

```bash
curl -X POST http://localhost:8000/stream/ask \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the financial highlights", "model": "qwen-qwq"}'
```

SSE events returned in order:
```
data: {"type": "meta",  "model_used": "qwen/qwen3-32b", "sources": ["report.pdf"], "relevance_score": 0.87}
data: {"type": "chunk", "content": "The financial highlights"}
data: {"type": "chunk", "content": " show strong growth..."}
data: {"type": "done",  "full_answer": "The financial highlights show strong growth..."}
```

### 5 — Query a specific file only

```bash
# Get file IDs
curl http://localhost:8000/files -H "Authorization: Bearer YOUR_TOKEN"

# Ask against file_id=2 only
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What does Q3 show?", "model": "llama-instant", "file_id": 2}'
```

### 6 — View metrics

```bash
curl http://localhost:8000/metrics?limit=10 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## AI Models

### Chat Models (user-selectable via `"model"` field)

| Key | Model | Speed | Best For |
|---|---|---|---|
| `llama-instant` *(default)* | Llama 3.1 8B Instant | Fastest | Quick Q&A, summaries, simple lookups |
| `qwen-qwq` | Qwen 3 32B | Slower | Complex analysis, multi-step reasoning, detailed answers |

### Vision Model (automatic — not user-selectable)

| Model | Trigger |
|---|---|
| Llama 4 Scout 17B | Automatically applied to every image, chart, or scanned page found during document upload |

---

## Supported File Types

| Format | Extension(s) | Extraction Method |
|---|---|---|
| PDF | `.pdf` | PyMuPDF text extraction + Tesseract OCR fallback for scanned pages + vision for embedded images |
| Word | `.docx` | python-docx (text, tables, embedded images via vision) |
| PowerPoint | `.pptx` | python-pptx (slides, text frames, tables, embedded images via vision) |
| Excel | `.xlsx`, `.xls` | pandas (all sheets) |
| CSV | `.csv` | Direct row-by-row parsing |
| Plain text | `.txt` | Direct read |
| OpenDocument | `.odt` | odfpy paragraph extraction |
| Images | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff` | Groq vision (Llama 4 Scout) |
| SQLite database | `.db` | Schema introspection + column stats + full row data |

---

## Metrics Explained

Every query automatically records:

| Metric | Description |
|---|---|
| `latency_ms` | End-to-end response time in milliseconds |
| `input_tokens` | Tokens sent to the LLM (prompt + context + history) |
| `output_tokens` | Tokens in the LLM's answer |
| `total_tokens` | `input_tokens + output_tokens` |
| `relevance_score` | Average cosine similarity (0–1) between query embedding and retrieved chunk embeddings |
| `source_count` | Number of documents referenced |
| `answer_length` | Character count of the final answer |

**Relevance score guide:**
- `0.0 – 0.35` — Low match (consider rephrasing)
- `0.35 – 0.60` — Good match (normal and expected for `all-MiniLM-L6-v2`)
- `0.60 – 1.0` — Strong semantic match

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Groq API key — get one free at [console.groq.com/keys](https://console.groq.com/keys) |

---

## Security

**Current implementation:**
- User-level data isolation — every FAISS chunk is tagged with `user_id`
- File-level isolation — every chunk is also tagged with `file_id`
- Bearer token authentication on all protected endpoints
- FAISS search filters strictly by `user_id` and optionally `file_id`

**Known limitations (MVP scope):**
- Passwords hashed with SHA-256 (production should use bcrypt/argon2 with salting)
- Tokens have no expiry (production should implement TTL)
- CORS currently set to `*` (should be restricted in production)

---

## Roadmap

- [ ] Token expiry and refresh flow
- [ ] Batch document upload with progress tracking
- [ ] Query result caching (repeated questions skip LLM call)
- [ ] Admin panel for system-wide monitoring
- [ ] Export chat transcripts as PDF or DOCX
- [ ] Cloud storage integration (Google Drive, S3)
- [ ] Switch FAISS index to `IndexIVFFlat` for large-scale deployments
- [ ] PostgreSQL support for production-grade persistence
- [ ] Rate limiting per user
- [ ] Multi-language document support

---

## Adding Screenshots

Place your screenshots in `assets/screenshots/` with these exact filenames:

| Filename | Content to capture |
|---|---|
| `upload.png` | File upload flow |
| `ask.png` | Asking a question and receiving an answer |
| `stream.png` | Streaming response in real time |
| `swagger.png` | Swagger UI (`/docs`) |
| `history.png` | Chat history view |
| `metrics.png` | Metrics / analytics output |

---

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [FAISS](https://github.com/facebookresearch/faiss) — Facebook AI Similarity Search
- [Groq](https://groq.com/) — Ultra-fast LLM inference
- [Sentence Transformers](https://www.sbert.net/) — High-quality semantic embeddings
- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF parsing

---

**Built by Deep Malviya**
