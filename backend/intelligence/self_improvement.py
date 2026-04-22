import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def critique_response(user_input, ora_response):
    if not GROQ_API_KEY:
        print("[SELF-IMPROVEMENT] GROQ_API_KEY not set. Skipping critique.")
        return []

    client = Groq(api_key=GROQ_API_KEY)

    critique_prompt = f"""
    You are an AI assistant tasked with critiquing another AI's response.
    Given the user's input and the AI's response, identify any issues with the response.
    Focus on accuracy, completeness, relevance, and adherence to instructions.
    List issues concisely, one per line.

    User Input: {user_input}
    AI Response: {ora_response}

    Critique:
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": critique_prompt}],
            max_tokens=200,
            temperature=0.5,
        )
        critique_text = response.choices[0].message.content.strip()
        return [line.strip() for line in critique_text.split('\n') if line.strip()]
    except Exception as e:
        print(f"[SELF-IMPROVEMENT ERROR] Critique failed: {e}")
        return []

def refine_response(user_input, original_response, issues):
    if not issues or not GROQ_API_KEY:
        return original_response

    client = Groq(api_key=GROQ_API_KEY)
    issues_str = "\n".join([f"- {issue}" for issue in issues])

    refine_prompt = f"""
    You are an AI assistant tasked with refining another AI's response.
    Given the user's input, the original AI's response, and a list of critiques, generate an improved response.

    User Input: {user_input}
    Original AI Response: {original_response}
    Critiques:
    {issues_str}

    Improved Response:
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": refine_prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[SELF-IMPROVEMENT ERROR] Refinement failed: {e}")
        return original_response
