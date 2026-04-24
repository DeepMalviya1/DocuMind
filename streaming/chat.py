# """
# streaming/chat.py

# Same as scripts/chat.py but as a standalone module for streaming folder.
# Uses shared processor singleton + user-selectable chat models.
# """

# import os
# from groq import Groq

# from scripts.processor import get_processor
# from scripts.prompts import build_prompt
# from scripts.models import get_chat_model_id, DEFAULT_CHAT_MODEL
# from scripts.log import get_logger
# from scripts import db

# logger = get_logger("StreamingChat")
# processor = get_processor()


# def get_groq_client():
#     api_key = os.getenv("SECRET_KEY")
#     if not api_key:
#         logger.error("SECRET_KEY not set")
#         return None
#     return Groq(api_key=api_key)


# def ask_stream(question, user_id, model=DEFAULT_CHAT_MODEL):
#     """
#     Stream answer using user-selected chat model.
#     model: "llama-instant" (fast) or "qwen-qwq" (advanced)
#     """
#     model_id = get_chat_model_id(model)
#     logger.info(f"user_id={user_id} | chat_model={model_id} | streaming | q={question}")

#     history = db.get_chat_history(user_id, limit=20)
#     results = processor.search(question, user_id, top_k=5)

#     if not results:
#         error_msg = "No documents have been uploaded yet. Please upload documents first."
#         db.save_message(user_id, "user", question)
#         db.save_message(user_id, "assistant", error_msg)
#         yield {"error": error_msg, "sources": [], "model_used": model_id}
#         return

#     context_parts, sources = [], []
#     for r in results:
#         context_parts.append(r["text"])
#         if r["source"] not in sources:
#             sources.append(r["source"])

#     context = "\n\n".join(context_parts)
#     yield {"sources": sources, "model_used": model_id}

#     system_message, user_message = build_prompt(
#         question=question, context=context,
#         sources=sources, chat_history=history
#     )

#     messages = [{"role": "system", "content": system_message}]
#     for msg in history:
#         messages.append({"role": msg["role"], "content": msg["content"]})
#     messages.append({"role": "user", "content": user_message})

#     client = get_groq_client()
#     if not client:
#         yield {"error": "SECRET_KEY not set.", "sources": sources, "model_used": model_id}
#         return

#     try:
#         stream = client.chat.completions.create(
#             model=model_id, messages=messages, max_tokens=2000, stream=True
#         )
#         full_answer = ""
#         for chunk in stream:
#             if chunk.choices[0].delta.content is not None:
#                 chunk_text = chunk.choices[0].delta.content
#                 full_answer += chunk_text
#                 yield {"chunk": chunk_text}

#         logger.info(f"Stream done ({len(full_answer)} chars) via {model_id}")
#         db.save_message(user_id, "user", question)
#         db.save_message(user_id, "assistant", full_answer)

#     except Exception as e:
#         logger.error(f"Streaming failed: {e}")
#         yield {"error": f"Error: {str(e)}", "sources": sources, "model_used": model_id}



"""
streaming/chat.py

Kept in sync with scripts/chat.py.
Re-exports functions so streaming/api.py can import without duplication.
All logic lives in scripts/chat.py.
"""

from scripts.chat import ask_stream, ask, process_document, clear_documents, clear_file_document

__all__ = ["ask_stream", "ask", "process_document", "clear_documents", "clear_file_document"]