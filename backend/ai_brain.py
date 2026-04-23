from groq import Groq
from config import GROQ_API_KEY
from context import build_system_prompt
import json

client = Groq(api_key=GROQ_API_KEY)


def ask_groq(user_text: str):
    """
    ORA AI brain using Groq (LLaMA 3)
    RETURNS STRUCTURED OUTPUT (SAFE FOR ORA PIPELINE)
    """

    try:
        # FIX: system prompt must NOT depend on user input
        system_prompt = build_system_prompt()

        messages = [
            {
                "role": "system",
                "content": system_prompt + """

Return ONLY valid JSON in this format:
{
  "reasoning": ["..."],
  "actions": ["..."]
}
"""
            },
            {
                "role": "user",
                "content": user_text
            }
        ]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        content = response.choices[0].message.content.strip()

        # SAFE PARSING LAYER
        try:
            return json.loads(content)
        except:
            return {
                "reasoning": ["invalid JSON from AI"],
                "actions": [],
                "raw": content
            }

    except Exception as e:
        print("[GROQ ERROR]", e)

        return {
            "reasoning": ["groq failure"],
            "actions": [],
            "error": str(e)
        }


# compatibility wrapper
def ask_gemini(user_text: str):
    return ask_groq(user_text)