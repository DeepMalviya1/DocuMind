"""
main.py

Entry point. Just starts the server.

Run:
    uvicorn main:app --reload
"""
from dotenv import load_dotenv
load_dotenv()

from scripts.api import app