def build_reasoning_messages(user_input, system_prompt):
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Understand the intent: {user_input}"},
        {"role": "user", "content": "Break the problem into steps."},
        {"role": "user", "content": "Plan the best response."},
        {"role": "user", "content": user_input},
    ]