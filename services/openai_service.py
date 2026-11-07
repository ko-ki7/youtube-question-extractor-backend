from openai import OpenAI
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

client = genai.GenerativeModel("gemini-1.5-flash")


def classify_question(comment: str) -> bool:
    prompt = f"""
あなたはYouTubeコメント分類AIです。

以下のコメントが質問なら true、
質問でなければ false を返してください。

コメント:
{comment}

回答:
"""

    response = client.generate_content(
        prompt
    )

    result = response.choices[0].message.content.strip()

    return result.lower() == "true"