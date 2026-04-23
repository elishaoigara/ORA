import time
import threading
from datetime import datetime, date


class AIBudgetController:
    def __init__(self,
                 daily_limit_tokens=100000,
                 soft_limit=80000,
                 estimated_tokens_per_call=800):

        self.daily_limit = daily_limit_tokens
        self.soft_limit = soft_limit
        self.estimated_tokens = estimated_tokens_per_call

        self.used_tokens = 0
        self.lock = threading.Lock()
        self.ai_enabled = True

        self.current_day = date.today()

    # ─────────────────────────────────────────
    # SAFE DAILY RESET (calendar-based)
    # ─────────────────────────────────────────
    def reset_if_new_day(self):
        today = date.today()

        if today != self.current_day:
            with self.lock:
                self.used_tokens = 0
                self.ai_enabled = True
                self.current_day = today
                print("[AI BUDGET] Daily reset completed")

    # ─────────────────────────────────────────
    # CHECK AI PERMISSION (FAST PATH)
    # ─────────────────────────────────────────
    def can_use_ai(self):
        self.reset_if_new_day()

        with self.lock:
            if not self.ai_enabled:
                return False

            return (self.used_tokens + self.estimated_tokens) <= self.daily_limit

    # ─────────────────────────────────────────
    # REGISTER USAGE (ATOMIC)
    # ─────────────────────────────────────────
    def register_call(self, tokens=None):
        cost = tokens or self.estimated_tokens

        with self.lock:
            if not self.ai_enabled:
                return False

            projected = self.used_tokens + cost

            # HARD STOP
            if projected >= self.daily_limit:
                self.used_tokens = self.daily_limit
                self.ai_enabled = False
                print("[AI BUDGET] HARD STOP REACHED")
                return False

            self.used_tokens = projected

            # soft limit behavior (IMPORTANT CHANGE)
            if self.used_tokens >= self.soft_limit:
                print("[AI BUDGET] WARNING: soft limit reached (throttling AI)")

                # optional throttle effect (NEW)
                self.ai_enabled = True
                time.sleep(0.2)  # small global slowdown signal

            return True

    # ─────────────────────────────────────────
    # OVERRIDE CONTROL
    # ─────────────────────────────────────────
    def force_enable(self):
        with self.lock:
            self.ai_enabled = True
            print("[AI BUDGET] Manual override enabled")


# GLOBAL INSTANCE
ai_budget = AIBudgetController()