def build_reasoning_messages(user_input: str, system_prompt: str) -> list[dict]:
    """
    Build a valid message list for chain-of-thought reasoning.
    Chat APIs require strict user/assistant alternation after the system message.
    We embed the reasoning steps into a single user message rather than
    sending multiple user messages in a row (which raises an API error).
    """
    reasoning_prompt = (
        f"Think step-by-step before answering.\n\n"
        f"Step 1 — Understand the intent: what is the user asking?\n"
        f"Step 2 — Break the problem into sub-problems if needed.\n"
        f"Step 3 — Plan the best response.\n"
        f"Step 4 — Answer the original question.\n\n"
        f"User question: {user_input}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": reasoning_prompt},
    ]
