"""
ORA AI Brain — Integrated with Budget Controller
- Document-first routing with confidence-based KB answers
- Smart truncation preserving sentence boundaries
- Caching for repeated queries
- Streaming support for long responses
- Budget-aware with token tracking
"""

import re
import json
import time
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
from context import build_system_prompt
from functools import lru_cache
from typing import Dict, Any, Optional, Generator, List, Tuple, Union
from ai_budget import ai_budget
from groq.types.chat import ChatCompletionMessageParam

# Initialize client
client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# KNOWLEDGE BASE MODULE LOADING (lazy import with fallbacks)
# ============================================================
_kb_module = None
_kb_search_func = None

def _get_kb_search():
    """Lazy load KB module - handles different import structures"""
    global _kb_module, _kb_search_func
    
    if _kb_search_func is not None:
        return _kb_search_func
    
    try:
        # Try the most common import pattern from your codebase
        from knowledge import pipeline
        
        # Check what functions exist in pipeline
        if hasattr(pipeline, 'search_and_format'):
            _kb_search_func = pipeline.search_and_format
            print("[KB] Using search_and_format")
        elif hasattr(pipeline, 'search'):
            _kb_search_func = pipeline.search # pyright: ignore[reportAttributeAccessIssue]
            print("[KB] Using search")
        else:
            # Fallback: look for any search function
            for attr_name in dir(pipeline):
                if 'search' in attr_name.lower() and callable(getattr(pipeline, attr_name)):
                    _kb_search_func = getattr(pipeline, attr_name)
                    print(f"[KB] Using {attr_name}")
                    break
        
        if _kb_search_func:
            return _kb_search_func
            
    except ImportError:
        pass
    
    try:
        # Try direct import from knowledge
        import knowledge
        if hasattr(knowledge, 'search_and_format'):
            _kb_search_func = knowledge.search_and_format
            print("[KB] Using knowledge.search_and_format")
            return _kb_search_func
        elif hasattr(knowledge, 'search'):
            _kb_search_func = knowledge.search # type: ignore
            print("[KB] Using knowledge.search")
            return _kb_search_func
    except ImportError:
        pass
    
    print("[KB] No KB search function found - KB features disabled")
    return None


def _get_kb_search_with_scores():
    """Get score-based search if available"""
    try:
        from knowledge import pipeline
        
        if hasattr(pipeline, 'search_with_scores'):
            return pipeline.search_with_scores # pyright: ignore[reportAttributeAccessIssue]
        elif hasattr(pipeline, 'search_with_relevance'):
            return pipeline.search_with_relevance # pyright: ignore[reportAttributeAccessIssue]
    except ImportError:
        pass
    return None


# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def _smart_truncate(text: str, max_chars: int, preserve_sentences: bool = True) -> str:
    """Smart truncation preserving semantic boundaries"""
    if not text or len(text) <= max_chars:
        return text
    
    if not preserve_sentences:
        return text[:max_chars] + "..."
    
    # Truncate at sentence boundary
    truncated = text[:max_chars]
    
    # Try to end at a complete sentence
    for boundary in ['. ', '! ', '? ', '\n\n', '\n']:
        last_boundary = truncated.rfind(boundary)
        if last_boundary > max_chars * 0.7:  # Keep if >70% of limit
            return truncated[:last_boundary + len(boundary)]
    
    # Fallback to word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.7:
        return truncated[:last_space] + "..."
    
    return truncated + "..."


def detect_intent(user_text: str) -> str:
    """Detect query intent for better routing"""
    intents = {
        "greeting": r"^(hi|hello|hey|good morning|good afternoon)",
        "farewell": r"(bye|goodbye|see you|see ya)",
        "help": r"(help|what can you do|capabilities|how to use)",
        "knowledge": r"(what is|how does|explain|define|describe|tell me about)",
        "action": r"(create|update|delete|save|write|add|remove)",
        "clarification": r"(what do you mean|could you explain|say again)"
    }
    
    user_lower = user_text.lower().strip()
    for intent, pattern in intents.items():
        if re.search(pattern, user_lower):
            return intent
    
    return "general"


# ============================================================
# KNOWLEDGE BASE ROUTING
# ============================================================
def _search_knowledge_base(query: str, n_results: int = 3) -> Tuple[Optional[str], Optional[float]]:
    """Search KB and return (context, max_confidence)"""
    search_func = _get_kb_search()
    
    if not search_func:
        return None, None
    
    try:
        # Try calling with different parameter patterns
        try:
            # Pattern 1: search_and_format(query, n_results)
            context = search_func(query, n_results=n_results)
        except TypeError:
            try:
                # Pattern 2: search(query, limit)
                context = search_func(query, limit=n_results) # type: ignore
            except TypeError:
                try:
                    # Pattern 3: search(query)
                    result = search_func(query)
                    if isinstance(result, str):
                        context = result
                    elif isinstance(result, list):
                        context = "\n\n---\n\n".join(str(r) for r in result[:n_results])
                    else:
                        context = str(result)
                except Exception:
                    # Pattern 4: Just call and hope for the best
                    context = search_func(query)
        
        if context and isinstance(context, str) and len(context.strip()) > 50:
            # Estimate confidence based on context length and query overlap
            confidence = min(0.85, len(context) / 1000)
            
            # Boost confidence if query terms appear in context
            query_terms = set(query.lower().split())
            context_lower = context.lower()
            matched_terms = sum(1 for term in query_terms if term in context_lower)
            if query_terms and matched_terms / len(query_terms) > 0.5:
                confidence = min(0.95, confidence + 0.1)
            
            return context, confidence
        
        return None, None
        
    except Exception as e:
        print(f"[KB SEARCH ERROR] {e}")
        return None, None


def _try_direct_kb_answer(user_text: str, confidence_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
    """
    Return complete answer if KB contains exact match with high confidence.
    Skips LLM entirely for FAQ-style questions.
    """
    search_with_scores = _get_kb_search_with_scores()
    search_func = _get_kb_search()
    
    content = None
    confidence = 0.0
    
    # Try score-based search first
    if search_with_scores:
        try:
            results = search_with_scores(user_text, n_results=1)
            if results and len(results) > 0:
                if isinstance(results[0], dict):
                    confidence = results[0].get('score', results[0].get('relevance', 0))
                    content = results[0].get('content', '')
                elif isinstance(results[0], tuple) and len(results[0]) >= 2:
                    content, confidence = results[0][0], results[0][1]
                else:
                    content = str(results[0])
                    confidence = 0.7
        except Exception as e:
            print(f"[KB SCORE SEARCH ERROR] {e}")
    
    # Fallback to regular search
    if not content and search_func:
        try:
            context, conf = _search_knowledge_base(user_text, n_results=1)
            if context:
                content = context
                confidence = conf or 0.7
        except Exception as e:
            print(f"[KB REGULAR SEARCH ERROR] {e}")
    
    # Check if we have a valid answer
    if content and confidence >= confidence_threshold and len(content) > 30 and len(content) < 2000:
        print(f"[KB DIRECT HIT] Confidence: {confidence:.2%}")
        # Register minimal token usage for KB hit
        ai_budget.register_call(tokens=50)
        return {
            "reasoning": ["direct_kb_match", f"confidence:{confidence:.2%}"],
            "actions": [],
            "reply": content,
            "source": "knowledge_base",
            "raw": content,
            "intent": detect_intent(user_text)
        }
    
    return None


@lru_cache(maxsize=100)
def _cached_kb_lookup(query: str) -> Tuple[Optional[str], Optional[float]]:
    """Cache KB results for identical queries"""
    return _search_knowledge_base(query)


# ============================================================
# GROQ API CALLS WITH BUDGET AWARENESS
# ============================================================
def _call_groq_with_retry(
    messages: List[ChatCompletionMessageParam],
    model: str,
    max_tokens: int,
    temperature: float = 0.4,
    retries: int = 2
) -> Any:
    """Call Groq API with budget check and basic retry"""
    
    # Check budget before making call
    if not ai_budget.can_use_ai():
        print("[AI BUDGET] Insufficient budget for Groq call")
        raise Exception("AI budget exhausted")
    
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # Register actual token usage with budget controller safely
            if response.usage is not None:
                total_tokens = response.usage.prompt_tokens + response.usage.completion_tokens
                ai_budget.register_call(tokens=total_tokens)
                print(f"[TOKEN USAGE] {total_tokens} tokens (prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens})")
            else:
                # Estimate if usage not provided
                ai_budget.register_call(tokens=max_tokens)
            
            return response
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Only retry on rate limits or timeouts
            if ("rate_limit" in error_str or "timeout" in error_str) and attempt < retries - 1:
                wait_time = (attempt + 1) * 2  # 2, 4 seconds
                print(f"[RETRY {attempt+1}/{retries}] {error_str[:50]}... Waiting {wait_time}s")
                time.sleep(wait_time)
                continue
            
            raise e


# ============================================================
# MAIN BRAIN FUNCTION
# ============================================================
def ask_groq(
    user_text: str, 
    use_kb: bool = True,
    confidence_threshold: float = 0.85
) -> Dict[str, Any]:
    """
    ORA AI brain — Budget-aware with KB routing.
    
    Args:
        user_text: User's query
        use_kb: Whether to search knowledge base
        confidence_threshold: Minimum confidence for direct KB answer
    
    Returns:
        Dict with reasoning, actions, and reply
    """
    
    # Check budget first
    if not ai_budget.can_use_ai():
        print("[AI BUDGET] AI disabled, using KB only")
        # Try KB even if AI is disabled
        direct_answer = _try_direct_kb_answer(user_text, confidence_threshold=0.6)  # Lower threshold when AI disabled
        if direct_answer:
            return direct_answer
        return {
            "reasoning": ["budget_exhausted", "no_kb_answer"],
            "actions": [],
            "reply": "I'm out of my daily token budget. Please try again tomorrow, or ask me something from our documentation.",
            "error": "budget_limit_reached"
        }
    
    # Step 1: Try direct KB answer (skip LLM entirely)
    if use_kb:
        direct_answer = _try_direct_kb_answer(user_text, confidence_threshold)
        if direct_answer:
            return direct_answer
    
    # Step 2: Get KB context for LLM synthesis
    kb_context = None
    kb_confidence = None
    
    if use_kb:
        kb_context, kb_confidence = _cached_kb_lookup(user_text)
        if kb_context:
            print(f"[KB CONTEXT] Retrieved {len(kb_context)} chars, confidence: {kb_confidence:.2%}")
    
    # Step 3: Build system prompt with KB context
    system_prompt = build_system_prompt(query=user_text)
    intent = detect_intent(user_text)
    
    if kb_context:
        # Smart truncation
        max_context_chars = 1200 if intent == "general" else 2000
        truncated_context = _smart_truncate(kb_context, max_context_chars)
        system_prompt += f"\n\n## RETRIEVED DOCUMENTS (confidence: {kb_confidence:.1%})\n{truncated_context}"
    
    # Properly typed messages for Groq API
    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    # Step 4: Choose model based on query length
    is_short = len(user_text.split()) < 12
    model = GROQ_MODEL_FALLBACK if is_short else GROQ_MODEL_PRIMARY
    max_tokens = 200 if is_short else 450
    
    print(f"[LLM CALL] Model: {model}, Max tokens: {max_tokens}, Intent: {intent}")
    
    # Step 5: Make API call with retry
    try:
        response = _call_groq_with_retry(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
            retries=2
        )
        
        content = response.choices[0].message.content
        if content is None:
            content = ""
        content = content.strip()
        
        # Try JSON parse (for structured pipeline usage)
        try:
            result = json.loads(content)
            result["raw"] = content
            result["intent"] = intent
            result["kb_used"] = kb_context is not None
            return result
        except json.JSONDecodeError:
            # Plain text response — wrap for pipeline compatibility
            return {
                "reasoning": ["direct_response", f"model:{model.split('/')[-1]}"],
                "actions": [],
                "reply": content,
                "raw": content,
                "intent": intent,
                "kb_used": kb_context is not None
            }
        
    except Exception as e:
        print(f"[GROQ ERROR] {e}")
        
        # Final fallback to minimal response (no second API call to preserve budget)
        return {
            "reasoning": ["groq_failure"],
            "actions": [],
            "error": str(e),
            "reply": "I'm having trouble processing that request. Please try rephrasing or check our documentation."
        }


# ============================================================
# STREAMING SUPPORT
# ============================================================
def ask_groq_stream(user_text: str, use_kb: bool = True) -> Generator[str, None, None]:
    """Stream response token by token for better UX"""
    
    # Check budget
    if not ai_budget.can_use_ai():
        yield "I'm out of my daily token budget. Please try again tomorrow."
        return
    
    # Try direct KB answer first
    if use_kb:
        direct_answer = _try_direct_kb_answer(user_text)
        if direct_answer:
            yield direct_answer["reply"]
            return
    
    # Get KB context
    kb_context = None
    if use_kb:
        kb_context, _ = _cached_kb_lookup(user_text)
    
    # Build prompt
    system_prompt = build_system_prompt(query=user_text)
    if kb_context:
        truncated_context = _smart_truncate(kb_context, 800)
        system_prompt += f"\n\n## RETRIEVED DOCUMENTS\n{truncated_context}"
    
    # Properly typed messages for streaming
    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    try:
        stream = client.chat.completions.create(
            model=GROQ_MODEL_FALLBACK,  # Use faster model for streaming
            messages=messages,
            temperature=0.4,
            max_tokens=450,
            stream=True
        )
        
        # Track approximate token usage (budget will be updated by non-streaming fallback)
        # Streaming doesn't provide usage stats, so we use estimate
        estimated_tokens = len(user_text) // 4 + 200
        ai_budget.register_call(tokens=estimated_tokens)
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        print(f"[STREAM ERROR] {e}")
        yield f"Sorry, I encountered an error: {str(e)[:100]}"


# ============================================================
# COMPATIBILITY WRAPPERS
# ============================================================
def ask_gemini(user_text: str) -> Dict[str, Any]:
    """Compatibility wrapper for Gemini (maps to Groq)"""
    return ask_groq(user_text)


def get_budget_status() -> dict:
    """Get current budget status from controller"""
    return ai_budget.get_status()


