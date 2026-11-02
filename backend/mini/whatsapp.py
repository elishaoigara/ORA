"""Optional, best-effort WhatsApp mirror for companion alerts via the WA bridge.

Disabled unless ORA_WA_NOTIFY_NUMBER (owner phone with country code, or an exact
WhatsApp contact name) is set and a bridge is reachable — either the embedded
bridge running inside this service (WA_EMBEDDED=1) or an explicit WA_SIDECAR_URL.
Never raises, performs no network I/O when unconfigured, and never logs secrets or
private chat data.
"""
import os


def sidecar_url():
    """Base URL of the WhatsApp bridge, or '' when none is configured."""
    url = os.getenv('WA_SIDECAR_URL', '').strip().rstrip('/')
    if url:
        return url
    # The embedded bridge only counts when it actually has its shared secret;
    # otherwise the mirror would claim to be enabled while nothing listens.
    if os.getenv('WA_EMBEDDED', '') == '1' and len(os.getenv('WA_API_SECRET', '').strip()) >= 12:
        port = os.getenv('WA_SIDECAR_PORT', '8080').strip() or '8080'
        return f'http://127.0.0.1:{port}'
    return ''


def configured():
    return bool(os.getenv('ORA_WA_NOTIFY_NUMBER', '').strip() and sidecar_url())


def notify(text):
    """Send one message to the owner through the bridge. Returns True when accepted."""
    if not configured():
        return False
    try:
        from connectors.whatsapp import send_message
        result = send_message(os.environ['ORA_WA_NOTIFY_NUMBER'].strip(), text)
        if not result.get('ok'):
            print('[WHATSAPP] send failed: bridge rejected the message')
            return False
        return True
    except Exception as exc:
        print(f'[WHATSAPP] send error: {type(exc).__name__}')
        return False
