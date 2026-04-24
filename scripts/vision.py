"""
vision.py

Uses Groq vision model (llama-4-scout) to describe images, charts and graphs.
Scout is the ONLY vision-capable model on Groq - always used here regardless
of what chat model the user has selected.
Falls back to OCR if Groq is not available.
"""

import os
import base64
import pytesseract
from PIL import Image
from groq import Groq
from dotenv import load_dotenv

from scripts.models import get_vision_model_id
from scripts.log import get_logger

load_dotenv()
logger = get_logger("Vision")


def get_groq_client():
    api_key = os.getenv("SECRET_KEY")
    if not api_key:
        logger.warning("SECRET_KEY not set, vision model will not work")
        return None
    return Groq(api_key=api_key)


def describe_image(image_path):
    """
    Describe an image using Groq vision (llama-4-scout).
    Falls back to OCR if Groq is unavailable.
    """
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return ""

    client = get_groq_client()
    if client:
        logger.info(f"Using vision model ({get_vision_model_id()}) for: {image_path}")
        return _describe_with_groq(client, image_path)

    logger.info(f"Groq not available, falling back to OCR for: {image_path}")
    return _describe_with_ocr(image_path)


def _describe_with_groq(client, image_path):
    """Send image to llama-4-scout (vision) and get rich description."""
    try:
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp":  "image/bmp",
            ".tiff": "image/tiff",
        }
        mime_type = mime_types.get(ext, "image/png")

        # Always use Scout for vision - it's the only model that supports images
        model_id = get_vision_model_id()

        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this image in detail. "
                                "If it is a chart or graph, describe the type, "
                                "axis labels, data values, and trends. "
                                "If it is a table, list all rows and columns. "
                                "If it contains text, include all the text. "
                                "Be precise with numbers and labels."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )

        description = response.choices[0].message.content
        logger.info(f"Vision model returned {len(description)} chars for {image_path}")
        return description.strip()

    except Exception as e:
        logger.error(f"Vision model failed: {e}, falling back to OCR")
        return _describe_with_ocr(image_path)


def _describe_with_ocr(image_path):
    """Fallback: extract text using OCR."""
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""