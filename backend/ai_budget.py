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

    def _reset_if_new_day_locked(self):
        """Must be called while holding self.lock."""
        today = date.today()
        if today != self.current_day:
            self.used_tokens = 0
            self.ai_enabled = True
            self.current_day = today
            print("[AI BUDGET] Daily reset completed")

    def can_use_ai(self):
        with self.lock:
            self._reset_if_new_day_locked()
            if not self.ai_enabled:
                return False
            return (self.used_tokens + self.estimated_tokens) <= self.daily_limit

    def register_call(self, tokens=None):
        cost = tokens or self.estimated_tokens

        with self.lock:
            self._reset_if_new_day_locked()

            if not self.ai_enabled:
                return False

            projected = self.used_tokens + cost

            if projected >= self.daily_limit:
                self.used_tokens = self.daily_limit
                self.ai_enabled = False
                print("[AI BUDGET] HARD STOP REACHED")
                return False

            self.used_tokens = projected

            if self.used_tokens >= self.soft_limit:
                print("[AI BUDGET] WARNING: soft limit reached (throttling AI)")
                # Note: sleep inside a lock is removed — it would block all
                # threads trying to check budget. Throttling is handled by
                # the AI cooldown in ai_gateway.py instead.

            return True

    def force_enable(self):
        with self.lock:
            self.ai_enabled = True
            print("[AI BUDGET] Manual override enabled")

    def get_status(self) -> dict:
        with self.lock:
            self._reset_if_new_day_locked()
            return {
                "used_tokens": self.used_tokens,
                "daily_limit": self.daily_limit,
                "soft_limit": self.soft_limit,
                "ai_enabled": self.ai_enabled,
                "usage_pct": round(self.used_tokens / self.daily_limit * 100, 1),
            }


# GLOBAL INSTANCE
ai_budget = AIBudgetController()
