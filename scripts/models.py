"""
models.py

Three models, three specific jobs:
  - VISION_MODEL   : llama-4-scout   → image/chart understanding (fixed, not user-selectable)
  - CHAT_MODELS    : qwen-qwq        → advanced reasoning (user choice)
                     llama-instant   → fastest responses  (user choice)
"""

# ── FIXED: always used for vision (images, charts, screenshots)
VISION_MODEL = {
    "id":          "meta-llama/llama-4-scout-17b-16e-instruct",
    "name":        "Llama 4 Scout",
    "description": "Vision-capable model. Used automatically for all images and charts."
}

# ── USER-SELECTABLE: for chat / Q&A
CHAT_MODELS = {
    "llama-instant": {
        "id":          "llama-3.1-8b-instant",
        "name":        "Llama Instant",
        "description": "Fastest responses. Great for quick, straightforward questions.",
        "speed":       "⚡ Fastest",
        "quality":     "★★★☆☆",
        "badge":       "Fast"
    },
    "qwen-qwq": {
        "id":          "qwen/qwen3-32b",
        "name":        "Qwen QwQ 32B",
        "description": "Deep reasoning model. Best for complex analysis and detailed answers.",
        "speed":       "🧠 Slower",
        "quality":     "★★★★★",
        "badge":       "Advanced"
    }
}

# Default chat model
DEFAULT_CHAT_MODEL = "llama-instant"


def get_vision_model_id() -> str:
    """Always returns Scout model ID for vision tasks."""
    return VISION_MODEL["id"]


def get_chat_model_id(model_key: str) -> str:
    """Return chat model ID. Falls back to default if invalid key."""
    model = CHAT_MODELS.get(model_key)
    if model:
        return model["id"]
    return CHAT_MODELS[DEFAULT_CHAT_MODEL]["id"]


def is_valid_chat_model(model_key: str) -> bool:
    return model_key in CHAT_MODELS