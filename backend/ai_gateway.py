import time
import threading
from queue import Queue, Empty
from ai_budget import ai_budget

COOLDOWN = 3
_last_call = 0

_ai_queue = Queue()
_lock = threading.Lock()

# result storage (thread-safe future-like object)
class ResultBox:
    def __init__(self):
        self.value = None
        self.event = threading.Event()


def _worker():
    global _last_call

    while True:
        try:
            fn, args, kwargs, box = _ai_queue.get()

            try:
                # cooldown enforcement
                now = time.time()
                if now - _last_call < COOLDOWN:
                    time.sleep(COOLDOWN - (now - _last_call))

                _last_call = time.time()

                result = fn(*args, **kwargs)
                ai_budget.register_call()

                box.value = result
                box.event.set()

            except Exception as e:
                box.value = {
                    "error": "AI_EXCEPTION",
                    "reasoning": [str(e)],
                    "actions": []
                }
                box.event.set()

            _ai_queue.task_done()

        except Exception as e:
            print("[AI WORKER CRASH]", e)
            time.sleep(1)


# start worker once
threading.Thread(target=_worker, daemon=True).start()


def safe_ai_call(ai_fn, *args, timeout=10, **kwargs):
    """
    ORA SAFE AI ENTRY POINT:
    - queued execution
    - timeout protection
    - budget control
    - no freeze guarantee
    """

    if not ai_budget.can_use_ai():
        return {
            "error": "AI_DISABLED_BUDGET",
            "reasoning": ["AI blocked by budget controller"],
            "actions": []
        }

    box = ResultBox()

    _ai_queue.put((ai_fn, args, kwargs, box))

    # wait safely with timeout
    if not box.event.wait(timeout=timeout):
        return {
            "error": "AI_TIMEOUT",
            "reasoning": ["AI request timed out"],
            "actions": []
        }

    return box.value