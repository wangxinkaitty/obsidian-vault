"""Quick check that .env loads and both APIs respond."""
import os
from dotenv import load_dotenv
from pyzotero import zotero
from openai import OpenAI

load_dotenv()

# Test Zotero
print("Testing Zotero API...")
zot = zotero.Zotero(
    library_id=os.getenv("ZOTERO_USER_ID"),
    library_type="user",
    api_key=os.getenv("ZOTERO_API_KEY"),
)
items = zot.items(limit=5)
print(f"  Found {len(items)} items in your library:")
for item in items:
    title = item["data"].get("title", "[no title]")
    print(f"    - {title[:80]}")

# Test DeepSeek
print("\nTesting DeepSeek API...")
llm = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
response = llm.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Reply with just the word 'connected'."}],
)
print(f"  LLM responded: {response.choices[0].message.content}")