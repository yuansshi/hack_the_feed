from openai import OpenAI
from pathlib import Path
import os

def get_key(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    for line in (Path(__file__).parent / "api_key.md").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise KeyError(name)

client = OpenAI(
    base_url="https://api.gmi-serving.com/v1",
    api_key=get_key("GMI_API_KEY"),
)

response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V4-Pro",
    messages=[{"role": "user", "content": "hi"}],
)

print(response.model)
print(response.choices[0].message.content)
