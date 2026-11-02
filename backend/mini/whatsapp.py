"""Optional, best-effort WhatsApp mirror for companion alerts via the owner's WA sidecar.

Disabled unless both ORA_WA_NOTIFY_NUMBER (owner phone with country code, or an exact
WhatsApp contact name) and WA_SIDECAR_URL (a reachable sidecar) are set. Never raises,
performs no network I/O when unconfigured, and never logs secrets or private chat data.
"""
import os


def configured():
    return bool(os.getenv('ORA_WA_NOTIFY_NUMBER', '').strip()
                and os.getenv('WA_SIDECAR_URL', '').strip())


def notify(text):
    """Send one message to the owner through the sidecar. Returns True when accepted."""
    if not configured():
        return False
    try:
        from connectors.whatsapp import send_message
        result = send_message(os.environ['ORA_WA_NOTIFY_NUMBER'].strip(), text)
        if not result.get('ok'):
            print('[WHATSAPP] send failed: sidecar rejected the message')
            return False
        return True
    except Exception as exc:
        print(f'[WHATSAPP] send error: {type(exc).__name__}')
        return False
