def critique_response(user_input, response):
    issues = []

    if len(response) < 30:
        issues.append("too short")

    if "i don't know" in response.lower():
        issues.append("low confidence")

    return issues


def refine_response(response, issues):
    if not issues:
        return response

    return response + "\n\n(Refined for clarity.)"