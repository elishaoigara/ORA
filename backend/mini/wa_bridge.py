"""Supervise the WhatsApp bridge inside the single Render Free service.

A WhatsApp bridge holds a linked-device socket, so it has to be running to be
useful. On Render Free that is unaffordable as a *second* service: the whole
workspace gets 750 instance hours a month, and one always-running service already
uses ~730 of them. So the bridge (Node + Baileys) runs as a supervised child of
the backend instead:

* one service, one set of instance hours;
* whenever ORA is awake, WhatsApp is reachable — no 12-second timeouts against a
  sleeping host, no cold start in the middle of sending a message;
* when ORA sleeps, the session lives in Postgres, so the bridge reconnects on the
  next wake without a new QR pairing.

Nothing is started unless ``WA_EMBEDDED=1`` and the credentials that make it
useful are present, so a deployment without WhatsApp behaves exactly as before.
"""
import asyncio
import os
import shutil
import time

DEFAULT_ENTRY = '/app/whatsapp-sidecar/src/server.js'
RESTART_MIN_SECONDS = 5.0
RESTART_MAX_SECONDS = 60.0
# A bridge that stayed up this long crashed for a real reason, not a boot race.
HEALTHY_AFTER_SECONDS = 45.0

_process = None


def entry():
    return os.getenv('WA_SIDECAR_ENTRY', DEFAULT_ENTRY).strip() or DEFAULT_ENTRY


def sidecar_port():
    return os.getenv('WA_SIDECAR_PORT', '8080').strip() or '8080'


def sidecar_base():
    """Base URL the backend uses to reach the bridge.

    An explicit WA_SIDECAR_URL always wins, which keeps the standalone sidecar
    deployment working unchanged. Otherwise the embedded bridge is addressed on
    loopback.
    """
    url = os.getenv('WA_SIDECAR_URL', '').strip().rstrip('/')
    if url:
        return url
    if os.getenv('WA_EMBEDDED', '') == '1':
        return f'http://127.0.0.1:{sidecar_port()}'
    return ''


def backend_base():
    """Loopback URL of this API, used by the bridge for webhooks and session sync."""
    explicit = os.getenv('ORA_BACKEND_URL', '').strip().rstrip('/')
    if explicit:
        return explicit
    return f"http://127.0.0.1:{os.getenv('PORT', '8000').strip() or '8000'}"


def enabled():
    """True when the bridge can actually link a device on this instance."""
    return (os.getenv('WA_EMBEDDED', '') == '1'
            and len(os.getenv('WA_API_SECRET', '').strip()) >= 12
            and len(os.getenv('ORA_INTERNAL_TOKEN', '').strip()) >= 16
            and os.path.exists(entry())
            and shutil.which('node') is not None)


# The child gets a filtered environment: it has no business holding DATABASE_URL,
# ORA_API_TOKEN, TELEGRAM_BOT_TOKEN or the model keys.
PASS_THROUGH = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TZ', 'NODE_OPTIONS', 'NODE_ENV')
BRIDGE_KEYS = ('ORA_BACKEND_URL', 'ORA_INTERNAL_TOKEN')


def child_env():
    """Environment for the child process.

    PORT must be overridden: Render hands the web service one port and the bridge
    would otherwise try to bind the same one. Only the backend port is public, so
    the bridge stays loopback-only and pairing is proxied by the API.
    """
    env = {key: value for key, value in os.environ.items()
           if key in PASS_THROUGH or key in BRIDGE_KEYS or key.startswith('WA_')}
    env['PORT'] = sidecar_port()
    env.setdefault('WA_AUTH_DIR', '/tmp/wa-auth')
    if not env.get('ORA_BACKEND_URL'):
        env['ORA_BACKEND_URL'] = backend_base()
    env.setdefault('WA_MAX_MESSAGES', '200')
    return env


async def supervise(log=print):
    """Run the bridge, restarting it if it exits. Cancelled on shutdown."""
    global _process
    if not enabled():
        return
    root = os.path.dirname(os.path.dirname(entry()))
    delay = RESTART_MIN_SECONDS
    while True:
        started = time.monotonic()
        reason = 'not started'
        try:
            _process = await asyncio.create_subprocess_exec(
                shutil.which('node'), entry(), cwd=root, env=child_env())
            log(f'[WA] bridge started (pid {_process.pid})')
            await _process.wait()
            reason = f'exit {_process.returncode}'
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # missing binary, permission problem, OOM
            reason = type(exc).__name__
        finally:
            _process = None
        if time.monotonic() - started >= HEALTHY_AFTER_SECONDS:
            delay = RESTART_MIN_SECONDS
        log(f'[WA] bridge stopped ({reason}); restarting in {delay:.0f}s')
        await asyncio.sleep(delay)
        delay = min(RESTART_MAX_SECONDS, delay * 2)


async def stop():
    """Terminate the child on shutdown so the platform can drain cleanly."""
    global _process
    process, _process = _process, None
    if not process or process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            process.kill()
        except ProcessLookupError:
            pass
