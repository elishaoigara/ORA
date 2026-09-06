import type { Op, Snapshot, Task } from "./api";
export function applyLocal(snapshot: Snapshot, op: Op): Snapshot {
  const next = {
    ...snapshot,
    tasks: snapshot.tasks.map((t) => ({ ...t })),
    memories: snapshot.memories.map((m) => ({ ...m })),
  };
  const p = op.payload;
  if (
    op.kind === "task.create" &&
    !next.tasks.some((t) => t.id === op.request_id)
  )
    next.tasks.push({
      id: op.request_id,
      title: String(p.title).trim(),
      due_at: p.due_at as string | null,
      priority: Number(p.priority || 2),
      repeat: String(p.repeat || "none"),
      done: false,
      version: 1,
    });
  const t = next.tasks.find((t) => t.id === p.id);
  if (t && t.version === p.version) {
    if (op.kind === "task.delete")
      next.tasks = next.tasks.filter((x) => x.id !== t.id);
    if (op.kind === "task.update")
      Object.assign(t, p, { version: t.version + 1 });
    if (op.kind === "task.complete") {
      if (!t.done && t.repeat && t.repeat !== "none" && t.due_at) {
        let date = Date.parse(t.due_at);
        const step = (t.repeat === "daily" ? 1 : 7) * 86400000;
        do {
          date += step;
        } while (date <= Date.now());
        t.due_at = new Date(date).toISOString();
      } else t.done = !t.done;
      t.version++;
    }
  }
  if (
    op.kind === "memory.save" &&
    !next.memories.some((m) => m.id === op.request_id)
  )
    next.memories.push({ id: op.request_id, text: String(p.text) });
  return next;
}
export function validateTask(p: Record<string, unknown>) {
  if (typeof p.title !== "string" || !p.title.trim() || p.title.length > 240)
    throw new Error("Enter a task title up to 240 characters.");
  if (p.due_at && !Number.isFinite(Date.parse(String(p.due_at))))
    throw new Error("Choose a valid reminder date.");
}
