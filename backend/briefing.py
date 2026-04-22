from datetime import datetime
from database import get_system_stats, get_tasks
from memory.profile import get_all_profile
from context import build_system_prompt
import json


def generate_briefing() -> str:
    now = datetime.now()
    day = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")

    lines = []

    # --- Header ---
    lines.append(f"👁 *Good morning, Elisha.*")
    lines.append(f"_{day} — {time_str}_\n")

    # --- System Status ---
    row = get_system_stats()
    if row:
        try:
            data = json.loads(row[0])
            cpu = data.get("cpu_percent", "?")
            ram = data.get("ram_percent", "?")
            disk = round(data.get("disk_free_gb", 0), 1)
            lines.append(f"🖥 *System*")
            lines.append(f"CPU: {cpu}% · RAM: {ram}% · Disk: {disk}GB free\n")
        except Exception:
            pass

    # --- Pending Tasks ---
    tasks = get_tasks("pending")
    if tasks:
        lines.append(f"📌 *Tasks ({len(tasks)} pending)*")
        for t in tasks[:5]:  # max 5 in briefing
            due = f" ⏰ {t[4][11:16]}" if t[4] else ""
            lines.append(f"• {t[1]}{due}")
        lines.append("")
    else:
        lines.append(f"📌 *Tasks*\nNo pending tasks.\n")

    # --- AI Note ---
    try:
        from groq import Groq
        from config import GROQ_API_KEY

        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)

            task_summary = ""
            if tasks:
                task_list = ", ".join([t[1] for t in tasks[:3]])
                task_summary = f"Pending tasks: {task_list}."

            prompt = (
                f"You are ORA, Elisha's personal assistant. "
                f"Write a short 2-3 sentence morning note for Elisha. "
                f"Today is {day}. {task_summary} "
                f"Be direct, personal, and motivating. No fluff."
            )

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.8,
            )

            note = response.choices[0].message.content.strip()
            lines.append(f"🧠 *ORA Note*\n{note}")

    except Exception as e:
        lines.append(f"🧠 *ORA Note*\nHave a productive day, Elisha.")

    return "\n".join(lines)


def send_morning_briefing():
    from telegram_bot import notify
    print("[ORA] Sending morning briefing...")
    briefing = generate_briefing()
    notify(briefing, is_alert=False)
    print("[ORA] Morning briefing sent.")
