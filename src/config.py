import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["LLM_API_KEY"]
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
