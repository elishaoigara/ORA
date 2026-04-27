from backend.api import app


import traceback


@app.get("/api/memory/learned")
def get_learned_facts_ep(category: str = None, limit: int = 30):
    """Facts ORA has learned from conversations over time."""
    try:
        from intelligence.learning_engine import get_learned_facts
        return get_learned_facts(category=category, limit=limit)
    except Exception:
        print(traceback.format_exc())
        return []