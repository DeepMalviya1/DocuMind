"""
chat.py

Context-aware Q&A with user-selectable chat models.
Vision is handled separately by vision.py using llama-4-scout.
Captures full metrics: latency, token usage, relevance score.
"""

import os
import time
import numpy as np
from groq import Groq

from scripts.processor import get_processor, EMBED_MODEL
from scripts.prompts import build_prompt
from scripts.models import get_chat_model_id, DEFAULT_CHAT_MODEL
from scripts.log import get_logger
from scripts import db

logger = get_logger("Chat")
processor = get_processor()


def get_groq_client():
    api_key = os.getenv("SECRET_KEY")
    if not api_key:
        logger.error("SECRET_KEY not set")
        return None
    return Groq(api_key=api_key)


def _compute_relevance_score(query, results):
    """
    Compute average cosine similarity between the query embedding
    and the retrieved chunk embeddings as a 0-1 relevance score.
    """
    if not results:
        return 0.0
    try:
        query_vec = EMBED_MODEL.encode([query])[0]
        chunk_vecs = EMBED_MODEL.encode([r["text"] for r in results])

        # Cosine similarity: dot / (norm * norm)
        scores = []
        for vec in chunk_vecs:
            dot = np.dot(query_vec, vec)
            norm = np.linalg.norm(query_vec) * np.linalg.norm(vec)
            scores.append(dot / norm if norm > 0 else 0.0)
        return float(np.mean(scores))
    except Exception:
        return 0.0


def ask(question, user_id, username="unknown", model=DEFAULT_CHAT_MODEL, file_id=None):
    """
    Answer a question using the user-selected chat model.
    model: "llama-instant" (fast) or "qwen-qwq" (advanced)
    file_id: if given, restricts search + history to that specific file/bot.
    Captures: latency, token usage, relevance score → saved to metrics DB.
    """
    model_id = get_chat_model_id(model)
    logger.info(f"user_id={user_id} | chat_model={model_id} | q={question}")

    history = db.get_chat_history(user_id, limit=20, file_id=file_id)
    results = processor.search(question, user_id, top_k=5, file_id=file_id)

    if not results:
        logger.warning("No relevant documents found")
        answer = "No documents have been uploaded yet. Please upload documents first."
        db.save_message(user_id, "user", question)
        db.save_message(user_id, "assistant", answer)
        return {"answer": answer, "sources": [], "model_used": model_id}

    context_parts, sources = [], []
    for r in results:
        context_parts.append(r["text"])
        if r["source"] not in sources:
            sources.append(r["source"])

    context = "\n\n".join(context_parts)
    relevance_score = _compute_relevance_score(question, results)

    system_message, user_message = build_prompt(
        question=question, context=context,
        sources=sources, chat_history=history
    )

    messages = [{"role": "system", "content": system_message}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    client = get_groq_client()
    if not client:
        return {"answer": "SECRET_KEY not set.", "sources": sources, "model_used": model_id}

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=model_id, messages=messages, max_tokens=2000
        )
        latency_ms = (time.time() - start_time) * 1000

        answer = response.choices[0].message.content.strip()

        # Extract token usage from Groq response
        usage = response.usage
        input_tokens  = usage.prompt_tokens     if usage else None
        output_tokens = usage.completion_tokens if usage else None
        total_tokens  = usage.total_tokens      if usage else None

        logger.info(
            f"Answer ready ({len(answer)} chars) via {model_id} | "
            f"latency={latency_ms:.0f}ms | tokens={total_tokens} | "
            f"relevance={relevance_score:.4f}"
        )

        db.save_message(user_id, "user", question, file_id=file_id)
        db.save_message(user_id, "assistant", answer, file_id=file_id)

        # Save full metrics
        db.save_metric(
            user_id=user_id, username=username, query=question,
            model_used=model_id, sources=sources,
            latency_ms=latency_ms,
            input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=total_tokens,
            relevance_score=relevance_score,
            answer_length=len(answer)
        )

        return {
            "answer":          answer,
            "sources":         sources,
            "model_used":      model_id,
            "latency_ms":      round(latency_ms, 2),
            "input_tokens":    input_tokens,
            "output_tokens":   output_tokens,
            "total_tokens":    total_tokens,
            "relevance_score": round(relevance_score, 4),
        }

    except Exception as e:
        logger.error(f"Chat model failed: {e}")
        return {"answer": f"Error: {str(e)}", "sources": sources, "model_used": model_id}


def ask_stream(question, user_id, username="unknown", model=DEFAULT_CHAT_MODEL, file_id=None):
    """
    Stream answer using the user-selected chat model.
    model: "llama-instant" (fast) or "qwen-qwq" (advanced)
    Yields dicts: {"sources", "model_used"} | {"chunk"} | {"error"}
    Captures: latency, token usage (estimated), relevance score.
    """
    model_id = get_chat_model_id(model)
    logger.info(f"user_id={user_id} | chat_model={model_id} | streaming | q={question}")

    history = db.get_chat_history(user_id, limit=20, file_id=file_id)
    results = processor.search(question, user_id, top_k=5, file_id=file_id)

    if not results:
        logger.warning("No relevant documents found")
        error_msg = "No documents have been uploaded yet. Please upload documents first."
        db.save_message(user_id, "user", question)
        db.save_message(user_id, "assistant", error_msg)
        yield {"error": error_msg, "sources": [], "model_used": model_id}
        return

    context_parts, sources = [], []
    for r in results:
        context_parts.append(r["text"])
        if r["source"] not in sources:
            sources.append(r["source"])

    context = "\n\n".join(context_parts)
    relevance_score = _compute_relevance_score(question, results)

    # First yield: sources + model info + relevance score
    yield {"sources": sources, "model_used": model_id, "relevance_score": round(relevance_score, 4)}

    system_message, user_message = build_prompt(
        question=question, context=context,
        sources=sources, chat_history=history
    )

    messages = [{"role": "system", "content": system_message}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    client = get_groq_client()
    if not client:
        yield {"error": "SECRET_KEY not set.", "sources": sources, "model_used": model_id}
        return

    try:
        start_time = time.time()
        stream = client.chat.completions.create(
            model=model_id, messages=messages, max_tokens=2000, stream=True
        )
        full_answer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                chunk_text = chunk.choices[0].delta.content
                full_answer += chunk_text
                yield {"chunk": chunk_text}

        latency_ms = (time.time() - start_time) * 1000

        # Estimate token counts for streaming (Groq doesn't return usage in stream mode)
        estimated_output = len(full_answer.split())
        estimated_input  = sum(len(m["content"].split()) for m in messages)

        logger.info(
            f"Streaming done ({len(full_answer)} chars) via {model_id} | "
            f"latency={latency_ms:.0f}ms | relevance={relevance_score:.4f}"
        )

        db.save_message(user_id, "user", question, file_id=file_id)
        db.save_message(user_id, "assistant", full_answer, file_id=file_id)

        # Save metrics
        db.save_metric(
            user_id=user_id, username=username, query=question,
            model_used=model_id, sources=sources,
            latency_ms=latency_ms,
            input_tokens=estimated_input, output_tokens=estimated_output,
            total_tokens=estimated_input + estimated_output,
            relevance_score=relevance_score,
            answer_length=len(full_answer)
        )

    except Exception as e:
        logger.error(f"Streaming failed: {e}")
        yield {"error": f"Error: {str(e)}", "sources": sources, "model_used": model_id}


def process_document(file_name, text, user_id, file_id=None):
    return processor.process(file_name, text, user_id, file_id=file_id)


def clear_documents(user_id):
    processor.clear_user(user_id)


def clear_file_document(user_id, file_id):
    processor.clear_file(user_id, file_id)