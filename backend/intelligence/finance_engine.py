import re
from database import log_event


MPESA_REGEX = r"Ksh([\d,]+\.\d{2}).*?from (.*?)\."


def parse_mpesa_sms(text):
    match = re.search(MPESA_REGEX, text)

    if not match:
        return None

    amount = float(match.group(1).replace(",", ""))
    sender = match.group(2)

    return {"amount": amount, "sender": sender}


def process_sms(text):
    data = parse_mpesa_sms(text)

    if not data:
        return None

    log_event("finance", data)
    return data


def analyze_spending(events):
    total = sum(e["amount"] for e in events)

    if total > 5000:
        return "⚠️ High spending today"

    return "Spending normal"