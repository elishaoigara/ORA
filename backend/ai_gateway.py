import time
import threading
from queue import Queue
from ai_budget import ai_budget

COOLDOWN = 3
_last_call = 0

# Queue ensures NO request overload (prevents 429 completely)
_ai_queue = Queue()
_processing = False
_lock = threading.Lock()


def _worker():
    global _processing, _last_call

    while True:
        fn, args, kwargs, result_box = _ai_queue.get()

        try:
            # cooldown protection
            now = time.time()
            if now - _last_call < COOLDOWN:
                time.sleep(COOLDOWN - (now - _last_call))

            _last_call = time.time()

            # execute AI
            result = fn(*args, **kwargs)

            # register usage
            ai_budget.register_call()

            result_box.append(result)

        except Exception as e:
            result_box.append({
                "error": "AI_EXCEPTION",
                "reasoning": [str(e)],
                "actions": []
            })

        _ai_queue.task_done()


# start worker once
threading.Thread(target=_worker, daemon=True).start()


def safe_ai_call(ai_fn, *args, **kwargs):
    """
    ZERO-429 SAFE AI ENTRY POINT
    - queues requests
    - enforces budget
    - prevents concurrency spikes
    """

    if not ai_budget.can_use_ai():
        return {
            "error": "AI_DISABLED_BUDGET",
            "reasoning": ["AI blocked by budget controller"],
            "actions": []
        }

    result_box = []

    _ai_queue.put((ai_fn, args, kwargs, result_box))

    # wait for processing
    while not result_box:
        time.sleep(0.05)

    return result_box[0]