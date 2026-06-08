from openai import OpenAI
from src import config

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
r = client.chat.completions.create(
    model=config.MODEL,
    messages=[{"role": "user", "content": "用一句话确认你在线"}],
)
print(r.choices[0].message.content)