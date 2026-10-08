import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
API_PORT = int(os.getenv("API_PORT", "8000"))
MAX_ASKS = 5
DEBUG_LLM = os.getenv("DEBUG_LLM", "") == "1"
