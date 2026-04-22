import time
import threading

# ─────────────────────────────────────────
# GLOBAL AI BUDGET CONTROLLER (HARD STOP)
# ─────────────────────────────────────────

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

        self.last_reset = time.time()

    # ─────────────────────────────────────────
    # DAILY RESET
    # ─────────────────────────────────────────
    def reset_if_new_day(self):
        if time.time() - self.last_reset > 86400:
            with self.lock:
                self.used_tokens = 0
                self.ai_enabled = True
                self.last_reset = time.time()
                print("[AI BUDGET] Daily reset completed")

    # ─────────────────────────────────────────
    # CHECK IF AI IS ALLOWED (SAFE VERSION)
    # ─────────────────────────────────────────
    def can_use_ai(self):
        self.reset_if_new_day()

        with self.lock:
            if not self.ai_enabled:
                return False

            # HARD SAFETY CHECK (before overflow)
            if self.used_tokens + self.estimated_tokens > self.daily_limit:
                self.ai_enabled = False
                print("[AI BUDGET] HARD STOP ACTIVATED (pre-check limit)")
                return False

            return True

    # ─────────────────────────────────────────
    # REGISTER AI USAGE (SAFE VERSION)
    # ─────────────────────────────────────────
    def register_call(self, tokens=None):
        with self.lock:
            cost = tokens or self.estimated_tokens

            # Prevent accidental overflow tracking
            if self.used_tokens + cost > self.daily_limit:
                self.used_tokens = self.daily_limit
                self.ai_enabled = False
                print("[AI BUDGET] HARD STOP (overflow prevented)")
                return False

            self.used_tokens += cost

            print(f"[AI BUDGET] Used: {self.used_tokens}/{self.daily_limit}")

            # Soft warning zone
            if self.used_tokens >= self.soft_limit:
                print("[AI BUDGET] WARNING: approaching limit")

            # Hard stop
            if self.used_tokens >= self.daily_limit:
                self.ai_enabled = False
                print("[AI BUDGET] AI DISABLED (hard limit reached)")

            return True

    # ─────────────────────────────────────────
    # MANUAL OVERRIDE
    # ─────────────────────────────────────────
    def force_enable(self):
        with self.lock:
            self.ai_enabled = True
            print("[AI BUDGET] Manual override enabled")


# GLOBAL INSTANCE
ai_budget = AIBudgetController()