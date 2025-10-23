import os
from huggingface_hub import InferenceClient

HF_API_KEY = os.getenv("HF_API_KEY")
client = InferenceClient(
    "huihui-ai/gemma-3-27b-it-abliterated",
    token=HF_API_KEY,
    timeout=120
)

try:
    response = client.chat.completions.create(
        model="huihui-ai/gemma-3-27b-it-abliterated",
        messages=[{"role": "user", "content": "سلام"}],
        temperature=0.5,
        top_p=0.7,
    )
    print("✅ مدل هوش مصنوعی پاسخ داد:", response.choices[0].message.content[:50])
except Exception as e:
    print(f"❌ خطا در فراخوانی مدل: {str(e)}")
