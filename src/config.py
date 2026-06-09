import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["LLM_API_KEY"]
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

EMBED_API_KEY = os.environ["EMBED_API_KEY"]
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-v3")

compress_token_threshold = 1500
lately_round = 3