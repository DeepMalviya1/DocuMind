"""
api.py

FastAPI endpoints:
    POST /register       - create a new account
    POST /login          - login and get a token
    POST /logout         - logout
    POST /upload         - upload and process files
    POST /ask            - ask (blocking) with model choice
    POST /stream/ask     - ask (streaming) with model choice
    GET  /models         - list available chat models
    GET  /history        - get chat history
    POST /clear-history  - clear chat history
    POST /clear          - clear all processed documents
"""

import os
import shutil
import json

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

from scripts.loader import DocumentLoader
from scripts.chat import ask, ask_stream, process_document, clear_documents, clear_file_document
from scripts.models import CHAT_MODELS, VISION_MODEL, DEFAULT_CHAT_MODEL, is_valid_chat_model
from scripts.log import get_logger
from scripts import db

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
app = FastAPI(
    title="Document Q&A API",
    description="""
## 📄 Document Q&A System with RAG + Streaming

Upload documents and ask questions. Powered by Groq LLM.

### 🤖 Available AI Models (for `/ask` and `/stream/ask`)

| Model Key | Name | Speed | Best For |
|-----------|------|-------|----------|
| `llama-instant` | Llama 3.1 8B Instant | ⚡ Fastest | Quick Q&A, summaries |
| `qwen-qwq` | Qwen QwQ 32B | 🧠 Slower | Complex analysis, deep reasoning |

### 👁️ Vision Model (automatic)
Images and charts are always processed using **Llama 4 Scout** automatically during upload. You don't need to select this.

### 🔑 Authentication
All endpoints (except `/register`, `/login`, `/models`) require a Bearer token.
1. Use `POST /login` to get a token
2. Click **Authorize** (top right) and enter: `Bearer YOUR_TOKEN`
    """,
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = get_logger("API")
loader = DocumentLoader()
security = HTTPBearer()

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        description="The question to ask about your uploaded documents",
        example="What is this document about?"
    )
    model: Literal["llama-instant", "qwen-qwq"] = Field(
        default="llama-instant",
        description=(
            "AI model to use for answering:\n\n"
            "- **llama-instant** → ⚡ Fastest responses. Best for simple, quick Q&A (default)\n"
            "- **qwen-qwq** → 🧠 Advanced reasoning. Best for complex analysis and deep questions"
        )
    )
    file_id: Optional[int] = Field(
        default=None,
        description=(
            "ID of the specific file to query (from GET /files).\n"
            "If provided, questions are answered using only that file's knowledge base.\n"
            "If omitted, all your uploaded files are searched together."
        )
    )


# ------------------------------------------------------------------
# Auth helper
# ------------------------------------------------------------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    user_info = db.verify_token(token)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_info


# ------------------------------------------------------------------
# GET /models  - what can user choose from?
# ------------------------------------------------------------------
@app.get("/models")
def list_models():
    """
    List available AI models.
    
    Chat models (user-selectable):
        - llama-instant : fastest, good for simple questions
        - qwen-qwq      : advanced reasoning, best for complex analysis
    
    Vision model (automatic, not user-selectable):
        - llama-4-scout : used automatically for all uploaded images/charts
    """
    return {
        "chat_models": {
            "description": "Choose one of these for your Q&A",
            "default": DEFAULT_CHAT_MODEL,
            "options": CHAT_MODELS
        },
        "vision_model": {
            "description": "Used automatically for images/charts (not user-selectable)",
            "model": VISION_MODEL
        }
    }


# ------------------------------------------------------------------
# POST /register
# ------------------------------------------------------------------
@app.post("/register")
def register(request: RegisterRequest):
    logger.info(f"Register: {request.username}")
    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not db.register_user(request.username, request.password):
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"message": f"User '{request.username}' registered successfully"}


# ------------------------------------------------------------------
# POST /login
# ------------------------------------------------------------------
@app.post("/login")
def login(request: LoginRequest):
    logger.info(f"Login: {request.username}")
    user_id = db.verify_user(request.username, request.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = db.create_token(user_id)
    return {"message": f"Welcome {request.username}", "user_id": user_id, "token": token}


# ------------------------------------------------------------------
# POST /logout
# ------------------------------------------------------------------
# @app.post("/logout")
# def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
#     token = credentials.credentials
#     user_info = db.verify_token(token)
#     if user_info is None:
#         raise HTTPException(status_code=401, detail="Invalid token")
#     db.delete_token(token)
#     return {"message": "Logged out successfully"}


# ------------------------------------------------------------------
# POST /upload
# ------------------------------------------------------------------
@app.post("/upload")
def upload_files(
    files: List[UploadFile] = File(...),
    user_info: dict = Depends(get_current_user)
):
    username = user_info["username"]
    user_id  = user_info["user_id"]
    logger.info(f"Upload: '{username}' uploading {len(files)} file(s)")

    results, errors = [], []

    for file in files:
        _, ext = os.path.splitext(file.filename)
        ext = ext.lower()

        if ext not in DocumentLoader.SUPPORTED:
            msg = f"Unsupported: {file.filename}"
            errors.append({"file": file.filename, "error": msg})
            continue

        file_path = os.path.join(DOCS_DIR, file.filename)
        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            content = loader.load(file_path)
            _, ext = os.path.splitext(file.filename)

            # Step 1: Register file first to get a stable file_id (chunk_count=0 placeholder)
            file_id = db.register_file(
                user_id=user_id,
                filename=file.filename,
                file_type=ext.lower().lstrip("."),
                char_count=len(content),
                chunk_count=0
            )

            # Step 2: Process with the real file_id — chunks are tagged correctly from the start
            chunk_count = process_document(file.filename, content, user_id, file_id=file_id)

            # Step 3: Update chunk count — same file_id is preserved (no new row, no id gap)
            db.register_file(
                user_id=user_id,
                filename=file.filename,
                file_type=ext.lower().lstrip("."),
                char_count=len(content),
                chunk_count=chunk_count or 0
            )

            results.append({
                "file":        file.filename,
                "file_id":     file_id,
                "file_type":   ext.lower().lstrip("."),
                "characters":  len(content),
                "chunk_count": chunk_count or 0,
                "content":     content
            })
        except Exception as e:
            errors.append({"file": file.filename, "error": str(e)})

    return {
        "uploaded_by":   username,
        "user_id":       user_id,
        "success_count": len(results),
        "error_count":   len(errors),
        "results":       results,
        "errors":        errors
    }


# ------------------------------------------------------------------
# POST /ask  (blocking)
# ------------------------------------------------------------------
@app.post("/ask")
def ask_question(
    request: AskRequest,
    user_info: dict = Depends(get_current_user)
):
    """
    Ask a question and get a complete answer (blocking).
    
    Model options:
        "llama-instant"  →  fastest, good for quick Q&A  (default)
        "qwen-qwq"       →  advanced reasoning, complex analysis
    
    Note: Images/charts in your documents are always processed using
    llama-4-scout (vision model) automatically during upload.
    """
    username = user_info["username"]
    user_id  = user_info["user_id"]

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    model = request.model if is_valid_chat_model(request.model) else DEFAULT_CHAT_MODEL
    logger.info(f"Ask: '{username}' | model={model} | q={request.question}")

    file_id = request.file_id
    if file_id is not None:
        file_info = db.get_file(user_id, file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found or does not belong to you")
    result = ask(request.question, user_id, username=username, model=model, file_id=file_id)

    return {
        "asked_by":       username,
        "question":       request.question,
        "model_used":     result["model_used"],
        "answer":         result["answer"],
        "sources":        result["sources"],
        "latency_ms":     result.get("latency_ms"),
        "input_tokens":   result.get("input_tokens"),
        "output_tokens":  result.get("output_tokens"),
        "total_tokens":   result.get("total_tokens"),
        "relevance_score":result.get("relevance_score"),
    }


# ------------------------------------------------------------------
# POST /stream/ask  (streaming SSE)
# ------------------------------------------------------------------
@app.post("/stream/ask")
async def ask_question_stream(
    request: AskRequest,
    user_info: dict = Depends(get_current_user)
):
    """
    Ask a question and get the answer streamed in real-time (SSE).
    
    Model options:
        "llama-instant"  →  fastest streaming  (default)
        "qwen-qwq"       →  deeper reasoning, streams slower
    
    SSE event types:
        {"type": "meta",  "model_used": "...", "sources": [...]}
        {"type": "chunk", "content": "..."}
        {"type": "done",  "full_answer": "..."}
        {"type": "error", "message": "..."}
    """
    username = user_info["username"]
    user_id  = user_info["user_id"]

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    model = request.model if is_valid_chat_model(request.model) else DEFAULT_CHAT_MODEL
    logger.info(f"Stream: '{username}' | model={model} | q={request.question}")

    async def generate():
        try:
            meta_sent   = False
            full_answer = ""

            for chunk_data in ask_stream(request.question, user_id, username=username, model=model, file_id=request.file_id):

                if "sources" in chunk_data and not meta_sent:
                    yield f"data: {json.dumps({'type': 'meta', 'model_used': chunk_data.get('model_used',''), 'sources': chunk_data['sources'], 'relevance_score': chunk_data.get('relevance_score')})}\n\n"
                    meta_sent = True

                if "chunk" in chunk_data:
                    full_answer += chunk_data["chunk"]
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_data['chunk']})}\n\n"

                if "error" in chunk_data:
                    yield f"data: {json.dumps({'type': 'error', 'message': chunk_data['error']})}\n\n"
                    return

            yield f"data: {json.dumps({'type': 'done', 'full_answer': full_answer})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


# ------------------------------------------------------------------
# GET /stream/health
# ------------------------------------------------------------------
# @app.get("/stream/health")
# async def streaming_health():
#     return {"status": "ok", "streaming_enabled": True}


# ------------------------------------------------------------------
# GET /history
# ------------------------------------------------------------------
@app.get("/history")
def get_history(
    file_id: int = None,
    user_info: dict = Depends(get_current_user)
):
    """
    Get chat history.
    - If file_id provided: history for that specific file's bot
    - If file_id is None: global history (messages not tied to any file)
    """
    history = db.get_chat_history(user_info["user_id"], limit=50, file_id=file_id)
    scope = f"file_id={file_id}" if file_id is not None else "global (no file)"
    return {
        "username":      user_info["username"],
        "scope":         scope,
        "message_count": len(history),
        "history":       history
    }


# ------------------------------------------------------------------
# POST /clear-history
# ------------------------------------------------------------------
# @app.post("/clear-history")
# def clear_history(user_info: dict = Depends(get_current_user)):
#     db.clear_chat_history(user_info["user_id"])
#     return {"message": "Chat history cleared"}


# ------------------------------------------------------------------
# POST /clear
# ------------------------------------------------------------------
# @app.post("/clear")
# def clear_all(user_info: dict = Depends(get_current_user)):
#     clear_documents(user_info["user_id"])
#     return {"message": "All processed documents cleared"}


# ------------------------------------------------------------------
# GET /metrics  - per-user query logs
# ------------------------------------------------------------------
@app.get("/metrics")
def get_my_metrics(
    limit: int = 50,
    user_info: dict = Depends(get_current_user)
):
    """
    Return the last N metric records for the current user.

    Each record includes:
      - query & timestamp
      - model used
      - latency_ms (response time)
      - input_tokens, output_tokens, total_tokens
      - relevance_score (0-1 cosine similarity of query vs retrieved chunks)
      - source_count, answer_length
    """
    rows = db.get_metrics(user_id=user_info["user_id"], limit=limit)
    return {
        "username":      user_info["username"],
        "record_count":  len(rows),
        "metrics":       rows
    }


# ------------------------------------------------------------------
# GET /metrics/summary  - aggregate stats for current user
# # ------------------------------------------------------------------
# @app.get("/metrics/summary")
# def get_my_metrics_summary(user_info: dict = Depends(get_current_user)):
#     """
#     Aggregated performance summary for the current user:
#       - total queries
#       - avg / min / max latency
#       - total token usage (input + output)
#       - avg relevance score
#       - avg answer length
#       - per-model breakdown
#     """
#     summary = db.get_metrics_summary(user_id=user_info["user_id"])
#     return {
#         "username": user_info["username"],
#         "summary":  summary
#     }


# ------------------------------------------------------------------
# GET /files  - list all files uploaded by current user
# ------------------------------------------------------------------
@app.get("/files")
def list_files(user_info: dict = Depends(get_current_user)):
    """
    List all files uploaded by the current user.
    Each file has its own isolated knowledge base and bot.

    Use the returned file_id in POST /ask or POST /stream/ask
    to talk to a specific file's assistant.
    """
    files = db.get_files(user_info["user_id"])
    return {
        "username":   user_info["username"],
        "file_count": len(files),
        "files":      files
    }


# ------------------------------------------------------------------
# GET /files/{file_id}  - info about one file
# ------------------------------------------------------------------
# @app.get("/files/{file_id}")
# def get_file_info(
#     file_id: int,
#     user_info: dict = Depends(get_current_user)
# ):
#     """Get details for a specific uploaded file."""
#     file_info = db.get_file(user_info["user_id"], file_id)
#     if not file_info:
#         raise HTTPException(status_code=404, detail="File not found")
#     return file_info


# ------------------------------------------------------------------
# DELETE /files/{file_id}  - delete a file and its knowledge base
# ------------------------------------------------------------------
# @app.delete("/files/{file_id}")
# def delete_file(
#     file_id: int,
#     user_info: dict = Depends(get_current_user)
# ):
#     """
#     Delete a specific file:
#       - Removes its chunks from the FAISS vector store
#       - Clears its chat history
#       - Removes it from the file registry
#     """
#     user_id = user_info["user_id"]
#     file_info = db.get_file(user_id, file_id)
#     if not file_info:
#         raise HTTPException(status_code=404, detail="File not found")

#     clear_file_document(user_id, file_id)
#     db.clear_chat_history(user_id, file_id=file_id)
#     db.delete_file(user_id, file_id)

#     return {"message": f"File '{file_info['filename']}' deleted successfully"}


# ------------------------------------------------------------------
# POST /files/{file_id}/clear-history  - reset chat for one file
# ------------------------------------------------------------------
# @app.post("/files/{file_id}/clear-history")
# def clear_file_history(
#     file_id: int,
#     user_info: dict = Depends(get_current_user)
# ):
#     """Clear the conversation history for a specific file's assistant."""
#     user_id = user_info["user_id"]
#     file_info = db.get_file(user_id, file_id)
#     if not file_info:
#         raise HTTPException(status_code=404, detail="File not found")

#     db.clear_chat_history(user_id, file_id=file_id)
#     return {"message": f"Chat history cleared for '{file_info['filename']}'"}