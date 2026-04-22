from groq import Groq
from config import GROQ_API_KEY
from context import build_system_prompt

client = Groq(api_key=GROQ_API_KEY)


def ask_groq(user_text: str):
    """
    ORA AI brain using Groq (LLaMA 3)
    """

    try:
        system_prompt = build_system_prompt(user_text)

        messages = [
            {
                "role": "system",
                "content": system_prompt
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

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("[GROQ ERROR]", e)
        return "ORA AI temporarily unavailable."