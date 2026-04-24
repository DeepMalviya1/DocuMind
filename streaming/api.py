"""
api.py (in streaming folder)

Streaming endpoints - to be included in main API
"""

import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from streaming.chat import ask_stream
from scripts.log import get_logger

logger = get_logger("StreamingAPI")

# Create a router
router = APIRouter(prefix="/stream", tags=["Streaming"])


# Request model
class AskRequest(BaseModel):
    question: str


@router.post("/ask")
async def ask_question_stream(request: AskRequest, req: Request):
    """
    Stream the answer in real-time as it's being generated.
    Returns Server-Sent Events (SSE) format.
    """
    # Get user_info from request state (injected by dependency)
    user_info = req.state.user_info if hasattr(req.state, 'user_info') else None
    
    if not user_info:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    username = user_info["username"]
    user_id = user_info["user_id"]

    logger.info(f"User '{username}' (id={user_id}) asked (streaming): {request.question}")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Generator function for streaming
    async def generate():
        try:
            sources_sent = False
            full_answer = ""

            # Stream the answer
            for chunk_data in ask_stream(request.question, user_id):
                if "sources" in chunk_data and not sources_sent:
                    # Send sources first
                    yield f"data: {json.dumps({'type': 'sources', 'sources': chunk_data['sources']})}\n\n"
                    sources_sent = True
                
                if "chunk" in chunk_data:
                    # Send answer chunks
                    chunk_text = chunk_data["chunk"]
                    full_answer += chunk_text
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_text})}\n\n"
                
                if "error" in chunk_data:
                    # Send error
                    yield f"data: {json.dumps({'type': 'error', 'message': chunk_data['error']})}\n\n"
                    return

            # Send completion signal
            yield f"data: {json.dumps({'type': 'done', 'full_answer': full_answer})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/health")
async def streaming_health():
    """
    Check if streaming functionality is available.
    """
    return {
        "status": "ok",
        "streaming_enabled": True,
        "endpoint": "/stream/ask"
    }