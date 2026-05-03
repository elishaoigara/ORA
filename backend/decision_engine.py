"""
ORA Decision Engine (Render Free Tier Optimized)

Design goals:
- Zero external calls by default
- Deterministic + fast (<1ms)
- Always returns structured decision output
- AI is optional and strictly gated
"""

def decide(context, use_ai=False, ai_handler=None):
    # ─────────────────────────────────────────
    # SAFE INPUT EXTRACTION
    # ─────────────────────────────────────────
    cpu = _safe_float(context.get("cpu"), 0)
    ram = _safe_float(context.get("ram"), 0)
    disk = _safe_float(context.get("disk_free_gb"), 999)

    # ─────────────────────────────────────────
    # ISSUE SCORING (CONSTANT TIME)
    # ─────────────────────────────────────────
    issues = []

    # CPU
    if cpu > 85:
        issues.append(("cpu", cpu, 5))
    elif cpu > 70:
        issues.append(("cpu", cpu, 3))

    # RAM
    if ram > 90:
        issues.append(("ram", ram, 5))
    elif ram > 75:
        issues.append(("ram", ram, 3))

    # Disk
    if disk < 5:
        issues.append(("disk", disk, 4))
    elif disk < 10:
        issues.append(("disk", disk, 2))

    # ─────────────────────────────────────────
    # SORT (MAX 3 ITEMS → trivial cost)
    # ─────────────────────────────────────────
    issues.sort(key=lambda x: x[2], reverse=True)

    # ─────────────────────────────────────────
    # STATE INFERENCE
    # ─────────────────────────────────────────
    if not issues:
        state = "healthy"
    elif any(score >= 5 for _, _, score in issues):
        state = "critical"
    else:
        state = "warning"

    # ─────────────────────────────────────────
    # PRIMARY FOCUS
    # ─────────────────────────────────────────
    primary = issues[0] if issues else None

    # ─────────────────────────────────────────
    # RISK DETECTION (COMBINED SIGNALS)
    # ─────────────────────────────────────────
    risks = []

    if cpu > 85 and ram > 90:
        risks.append("System overload risk")

    if disk < 5:
        risks.append("Disk exhaustion risk")

    # ─────────────────────────────────────────
    # ACTION GENERATION (LIMITED)
    # ─────────────────────────────────────────
    actions = []

    if primary:
        metric, value, score = primary

        if metric == "cpu":
            actions.append({
                "type": "alert",
                "message": f"Reduce CPU load ({value:.0f}%)",
                "severity": "high" if score >= 5 else "medium"
            })

        elif metric == "ram":
            actions.append({
                "type": "alert",
                "message": f"Reduce memory usage ({value:.0f}%)",
                "severity": "high" if score >= 5 else "medium"
            })

        elif metric == "disk":
            actions.append({
                "type": "alert",
                "message": f"Free disk space ({value:.1f}GB left)",
                "severity": "high" if score >= 4 else "medium"
            })

    # ─────────────────────────────────────────
    # REASONING (COMPRESSED)
    # ─────────────────────────────────────────
    reasoning = [f"System state: {state}"]

    if primary:
        reasoning.append(f"Primary issue: {primary[0]} ({primary[1]})")

    if risks:
        reasoning.extend(risks)

    if not issues:
        reasoning.append("All systems normal")

    # ─────────────────────────────────────────
    # AI FALLBACK (STRICT + SAFE + CHEAP)
    # ─────────────────────────────────────────
    borderline = (
        (70 < cpu <= 85) or
        (75 < ram <= 90) or
        (5 <= disk <= 10)
    )

    if (
        use_ai
        and ai_handler
        and not primary  # only if no strong issue
        and borderline
    ):
        try:
            ai_result = ai_handler({
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "state": state
            })

            if isinstance(ai_result, dict):
                # Merge safely (no overwrite of core logic)
                reasoning.extend(ai_result.get("reasoning", [])[:2])
                actions.extend(ai_result.get("actions", [])[:2])

        except Exception:
            reasoning.append("AI fallback failed (ignored)")

    # ─────────────────────────────────────────
    # FINAL OUTPUT (STABLE CONTRACT)
    # ─────────────────────────────────────────
    return {
        "state": state,
        "primary_focus": primary[0] if primary else None,
        "issues": issues[:3],        # capped → low payload
        "risks": risks[:2],          # capped
        "actions": actions[:3],      # capped
        "reasoning": reasoning[:5]   # capped
    }


# ─────────────────────────────────────────
# UTILITIES (SAFE + FAST)
# ─────────────────────────────────────────
def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default