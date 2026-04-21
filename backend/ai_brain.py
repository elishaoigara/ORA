from google import genai
from config import GEMINI_API_KEY
from context import build_system_prompt

client = genai.Client(api_key=GEMINI_API_KEY)

def ask_gemini(user_text: str):
    """
    Sends ORA context + user input to Gemini
    Returns intelligent response
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_text,
        config={
            "system_instruction": build_system_prompt(),
            "temperature": 0.7,
            "max_output_tokens": 500
        }
    )

    return response.text