import React, { useCallback, useState } from "react";
import {
  ScrollView,
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  Switch,
  Linking,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { useShareIntentContext } from "expo-share-intent";
import * as DocumentPicker from "expo-document-picker";
import { request, makeId, readLocal, writeLocal } from "@/lib/mini/api";
import { colors as c } from "@/lib/mini/theme";
const empty: any = {
  name: "",
  repository: "",
  goal: "",
  next_step: "",
  blockers: "",
  branch: "",
  github_alerts: false,
  archived: false,
};
function Button({
  title,
  onPress,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      style={[s.button, disabled && { opacity: 0.4 }]}
      onPress={onPress}
    >
      <Text style={s.buttonText}>{title}</Text>
    </Pressable>
  );
}
function Field({
  label,
  value,
  onChange,
  multiline = false,
}: {
  label: string;
  value: string;
  onChange: (s: string) => void;
  multiline?: boolean;
}) {
  return (
    <View>
      <Text style={s.small}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        style={[
          s.input,
          multiline && { minHeight: 90, textAlignVertical: "top" },
        ]}
        value={value || ""}
        onChangeText={onChange}
        multiline={multiline}
        autoCapitalize="none"
      />
    </View>
  );
}
export default function Work() {
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const { hasShareIntent, shareIntent, resetShareIntent } =
    useShareIntentContext();
  const [data, setData] = useState<any>({
      projects: [],
      facts: [],
      documents: [],
      events: [],
    }),
    [desktop, setDesktop] = useState<any>({ workers: [], jobs: [] });
  const [project, setProject] = useState<any>(empty),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [cached, setCached] = useState(false);
  const [fact, setFact] = useState<any>({
      text: "",
      source: "Owner note",
      expires_at: "",
    }),
    [prompt, setPrompt] = useState(""),
    [reply, setReply] = useState("");
  const [attachments, setAttachments] = useState<string[]>([]),
    [resume, setResume] = useState<any>(null);
  const [job, setJob] = useState({
    worker_id: "",
    repository: "",
    check: "",
    base_sha: "",
    patch: "",
  });
  const refresh = useCallback(async () => {
    const [w, d] = await Promise.all([
      request<any>("/work"),
      request<any>("/desktop"),
    ]);
    setData(w);
    setDesktop(d);
    setCached(false);
    await writeLocal("work", w);
  }, []);
  useFocusEffect(
    useCallback(() => {
      let active = true;
      readLocal<any>("work", null)
        .then((d) => {
          if (d && active) {
            setData(d);
            setCached(true);
          }
        })
        .then(() => refresh())
        .catch((e) => setError(e.message));
      return () => {
        active = false;
      };
    }, [refresh]),
  );
  async function run(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function choose(p: any) {
    setProject(p);
    setResume(null);
    setReply("");
    setAttachments([]);
    setFact({ text: "", source: "Owner note", expires_at: "" });
  }
  const worker = desktop.workers.find((w: any) => w.id === job.worker_id);
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
      >
        <Button title="Back to ORA" onPress={() => router.back()} />
        <Text style={s.title}>Projects & desktop</Text>
        <Text style={s.text}>
          Your decisions, next steps and work evidence in one place.
        </Text>
        {cached && (
          <Text style={s.small}>
            Saved snapshot — reconnect before making changes.
          </Text>
        )}
        {!!error && (
          <Text accessibilityRole="alert" style={s.error}>
            {error}
          </Text>
        )}
        <Button
          title={busy ? "Working…" : "Refresh activity"}
          disabled={busy}
          onPress={() => run(refresh)}
        />
        <View style={s.card}>
          <Text style={s.heading}>Your projects</Text>
          <Button
            title="+ New project"
            disabled={busy}
            onPress={() => choose(empty)}
          />
          {data.projects.map((p: any) => (
            <Button
              key={p.id}
              title={`${p.id === project.id ? "● " : ""}${p.name}${p.archived ? " · archived" : ""}`}
              disabled={busy}
              onPress={() => choose(p)}
            />
          ))}
        </View>
        <View style={s.card}>
          <Text style={s.heading}>
            {project.id ? "Project workspace" : "Create a project"}
          </Text>
          {Object.entries({
            name: "Project name",
            repository: "GitHub owner/repository",
            goal: "Goal",
            next_step: "Next step",
            blockers: "Blockers",
            branch: "Working branch",
          }).map(([k, label]) => (
            <Field
              key={k}
              label={label}
              value={project[k]}
              onChange={(v) => setProject({ ...project, [k]: v })}
              multiline={["goal", "next_step", "blockers"].includes(k)}
            />
          ))}
          <Text style={s.text}>GitHub alerts for this repository</Text>
          <Switch
            value={project.github_alerts}
            onValueChange={(v) => setProject({ ...project, github_alerts: v })}
          />
          <Text style={s.text}>Archived</Text>
          <Switch
            value={project.archived}
            onValueChange={(v) => setProject({ ...project, archived: v })}
          />
          <Button
            title="Save project"
            disabled={busy || !project.name.trim()}
            onPress={() =>
              run(async () =>
                setProject(
                  await request("/work/projects", {
                    ...project,
                    request_id: makeId(),
                  }),
                ),
              )
            }
          />
        </View>
        {project.id && (
          <>
            <View style={s.card}>
              <Text style={s.heading}>Resume my work</Text>
              <Button
                title="Show saved context"
                disabled={busy}
                onPress={() =>
                  run(async () =>
                    setResume(
                      await request(`/work/projects/${project.id}/resume`),
                    ),
                  )
                }
              />
              {resume && (
                <>
                  <Text style={s.text}>
                    Goal: {resume.project.goal || "Not set"}
                    {"\n\n"}Next: {resume.project.next_step || "Not set"}
                    {"\n\n"}Blockers:{" "}
                    {resume.project.blockers || "None recorded"}
                  </Text>
                  <Text style={s.small}>
                    Saved {new Date(resume.project.updated_at).toLocaleString()}{" "}
                    · {resume.facts.length} active facts
                  </Text>
                  {resume.messages?.map((m: any) => (
                    <View key={m.id} style={s.article}>
                      <Text style={s.small}>{m.role}</Text>
                      <Text selectable style={s.text}>
                        {m.text}
                      </Text>
                    </View>
                  ))}
                </>
              )}
            </View>
            <View style={s.card}>
              <Text style={s.heading}>Decisions & memory</Text>
              <Field
                label="Fact or decision"
                value={fact.text}
                multiline
                onChange={(v) => setFact({ ...fact, text: v })}
              />
              <Field
                label="Source"
                value={fact.source}
                onChange={(v) => setFact({ ...fact, source: v })}
              />
              <Field
                label="Optional expiry (e.g. 2026-12-31T18:00:00+03:00)"
                value={fact.expires_at}
                onChange={(v) => setFact({ ...fact, expires_at: v })}
              />
              <Button
                title={fact.id ? "Save correction" : "Remember this"}
                disabled={busy || !fact.text.trim()}
                onPress={() =>
                  run(async () => {
                    await request("/work/facts", {
                      ...fact,
                      expires_at: fact.expires_at || null,
                      project_id: project.id,
                      request_id: makeId(),
                    });
                    setFact({ text: "", source: "Owner note", expires_at: "" });
                  })
                }
              />
              {data.facts
                .filter((f: any) => f.project_id === project.id)
                .map((f: any) => (
                  <View key={f.id} style={s.article}>
                    <Text selectable style={s.text}>
                      {f.text}
                    </Text>
                    <Text style={s.small}>
                      {f.source} · {new Date(f.updated_at).toLocaleString()}
                      {f.expires_at
                        ? ` · ${new Date(f.expires_at) < new Date() ? "Expired" : "Expires"} ${new Date(f.expires_at).toLocaleString()}`
                        : ""}
                    </Text>
                    <Button
                      title="Correct"
                      disabled={busy}
                      onPress={() =>
                        setFact({ ...f, expires_at: f.expires_at || "" })
                      }
                    />
                    <Button
                      title="Forget"
                      disabled={busy}
                      onPress={() =>
                        run(() =>
                          request("/work/facts", {
                            ...f,
                            deleted: true,
                            request_id: makeId(),
                          }),
                        )
                      }
                    />
                  </View>
                ))}
            </View>
            <View style={s.card}>
              <Text style={s.heading}>Ask ORA about this project</Text>
              {hasShareIntent && shareIntent.files?.length ? (
                <Button
                  title={`Import shared file: ${shareIntent.files[0].fileName}`}
                  disabled={busy}
                  onPress={() =>
                    run(async () => {
                      const f = shareIntent.files![0];
                      if (f.size && f.size > 2 * 1024 * 1024)
                        throw new Error("Choose a file under 2 MB.");
                      const form = new FormData();
                      form.append("file", {
                        uri: f.path,
                        name: f.fileName,
                        type: f.mimeType,
                      } as any);
                      form.append("project_id", project.id);
                      const d = await request<any>("/work/attachments", form);
                      setAttachments([d.id]);
                      resetShareIntent();
                    })
                  }
                />
              ) : null}
              <Text style={s.small}>
                Choose PNG/JPEG, text, Markdown, CSV, logs or readable PDF,
                under 2 MB. Images go to the vision provider; only the generated
                description is saved.
              </Text>
              <Button
                title="Choose an image or document"
                disabled={busy}
                onPress={() =>
                  run(async () => {
                    const r = await DocumentPicker.getDocumentAsync({
                      type: [
                        "image/png",
                        "image/jpeg",
                        "application/pdf",
                        "text/*",
                      ],
                      copyToCacheDirectory: true,
                    });
                    if (r.canceled) return;
                    const a = r.assets[0];
                    if (a.size && a.size > 2 * 1024 * 1024)
                      throw new Error("Choose a file under 2 MB.");
                    const form = new FormData();
                    form.append("file", {
                      uri: a.uri,
                      name: a.name,
                      type: a.mimeType || "application/octet-stream",
                    } as any);
                    form.append("project_id", project.id);
                    const d = await request<any>("/work/attachments", form);
                    setAttachments([d.id]);
                  })
                }
              />
              {data.documents
                .filter((d: any) => d.project_id === project.id)
                .map((d: any) => (
                  <View key={d.id} style={s.article}>
                    <Button
                      title={`${attachments.includes(d.id) ? "✓ " : ""}${d.name}`}
                      disabled={
                        busy ||
                        (!attachments.includes(d.id) && attachments.length >= 3)
                      }
                      onPress={() =>
                        setAttachments(
                          attachments.includes(d.id)
                            ? attachments.filter((x) => x !== d.id)
                            : [...attachments, d.id],
                        )
                      }
                    />
                    {d.analysis_kind === "ai_image_description" && (
                      <Text style={s.small}>
                        AI-generated image description; may contain errors.
                      </Text>
                    )}
                    <Button
                      title="Remove document"
                      disabled={busy}
                      onPress={() =>
                        run(async () => {
                          await request("/operations", {
                            kind: "document.delete",
                            payload: { id: d.id },
                            request_id: makeId(),
                          });
                          setAttachments((a) => a.filter((x) => x !== d.id));
                        })
                      }
                    />
                  </View>
                ))}
              <Field
                label="Your question"
                value={prompt}
                onChange={setPrompt}
                multiline
              />
              <Button
                title="Ask ORA"
                disabled={busy || !prompt.trim()}
                onPress={() =>
                  run(async () => {
                    const r = await request<any>("/chat", {
                      text: prompt,
                      project_id: project.id,
                      document_ids: attachments,
                      request_id: makeId(),
                    });
                    setReply(r.reply);
                    setPrompt("");
                  })
                }
              />
              {!!reply && (
                <Text selectable style={s.text}>
                  {reply}
                </Text>
              )}
              <Button
                title="Review tool actions"
                onPress={() => router.push("/tools")}
              />
            </View>
            <View style={s.card}>
              <Text style={s.heading}>GitHub updates</Text>
              {data.events
                .filter(
                  (e: any) =>
                    e.repository.toLowerCase() ===
                    project.repository.toLowerCase(),
                )
                .slice()
                .reverse()
                .map((e: any) => (
                  <View key={e.id} style={s.article}>
                    <Button
                      title={e.title}
                      onPress={() => Linking.openURL(e.url)}
                    />
                    <Text style={s.small}>
                      {new Date(e.created_at).toLocaleString()}
                    </Text>
                  </View>
                ))}
              <Text style={s.small}>
                Webhook setup is required. Push follows your quiet hours and the
                notification scheduler.
              </Text>
            </View>
          </>
        )}
        <View style={s.card}>
          <Text style={s.heading}>Connections</Text>
          <Button
            title="Test connections"
            disabled={busy}
            onPress={() =>
              run(async () =>
                setDiagnostics(await request("/work/diagnostics", {})),
              )
            }
          />
          {diagnostics?.checks.map((check: any) => (
            <Text key={check.name} style={s.text}>
              {check.name}: {check.status}
              {"\n"}
              {check.detail}
            </Text>
          ))}
          <Text style={s.text}>
            GitHub token:{" "}
            {data.connections?.github_token_configured
              ? "configured"
              : "missing"}
            {"\n"}Webhook:{" "}
            {data.connections?.webhook_configured ? "configured" : "missing"}
            {"\n"}Image analysis:{" "}
            {data.connections?.vision_configured ? "configured" : "missing"}
          </Text>
          <Text style={s.small}>
            Configuration is not a live connection test. Try a repository read
            in Tools & GitHub or upload an image.
          </Text>
          <Text style={s.heading}>Your computers</Text>
          <Text style={s.small}>
            Create a one-time worker pairing code from the web workspace.
          </Text>
          {desktop.workers.map((w: any) => (
            <View key={w.id} style={s.article}>
              <Text style={s.text}>
                {w.label} ·{" "}
                {w.revoked ? "revoked" : w.online ? "online" : "offline"}
              </Text>
            </View>
          ))}
        </View>
        {project.id && (
          <View style={s.card}>
            <Text style={s.heading}>Queue a desktop check</Text>
            <Text style={s.small}>
              Select a computer, repository and check. The computer asks for
              local approval before executing repository code.
            </Text>
            {desktop.workers
              .filter((w: any) => !w.revoked)
              .map((w: any) => (
                <Button
                  key={w.id}
                  title={`${job.worker_id === w.id ? "● " : ""}${w.label}`}
                  disabled={busy}
                  onPress={() =>
                    setJob({
                      ...job,
                      worker_id: w.id,
                      repository: "",
                      check: "",
                    })
                  }
                />
              ))}
            {Object.keys(worker?.repositories || {}).map((r) => (
              <Button
                key={r}
                title={`${job.repository === r ? "● " : ""}${r}`}
                disabled={busy}
                onPress={() => setJob({ ...job, repository: r, check: "" })}
              />
            ))}
            {(worker?.repositories[job.repository] || []).map((v: string) => (
              <Button
                key={v}
                title={`${job.check === v ? "● " : ""}${v}`}
                disabled={busy}
                onPress={() => setJob({ ...job, check: v })}
              />
            ))}
            <Field
              label="Optional patch base SHA"
              value={job.base_sha}
              onChange={(v) => setJob({ ...job, base_sha: v })}
            />
            <Field
              label="Optional Git unified diff"
              value={job.patch}
              onChange={(v) => setJob({ ...job, patch: v })}
              multiline
            />
            <Button
              title="Queue for local approval"
              disabled={busy || !job.check}
              onPress={() =>
                run(() =>
                  request("/desktop/jobs", {
                    ...job,
                    project_id: project.id,
                    request_id: makeId(),
                  }),
                )
              }
            />
          </View>
        )}
        <View style={s.card}>
          <Text style={s.heading}>Desktop activity</Text>
          {desktop.jobs
            .slice()
            .reverse()
            .map((j: any) => (
              <View key={j.id} style={s.article}>
                <Text style={s.heading}>
                  {j.repository} · {j.check}
                </Text>
                <Text selectable style={s.small}>
                  {j.status} · Job {j.id}
                </Text>
                {j.has_result && (
                  <Button
                    title="Load full result"
                    disabled={busy}
                    onPress={async () => {
                      setBusy(true);
                      try {
                        const full = await request<any>(
                          `/desktop/jobs/${j.id}`,
                        );
                        setDesktop((d: any) => ({
                          ...d,
                          jobs: d.jobs.map((row: any) =>
                            row.id === j.id ? full : row,
                          ),
                        }));
                      } catch (e: any) {
                        setError(e.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  />
                )}
                <Text selectable style={s.text}>
                  {j.summary}
                </Text>
                {!!j.diff && (
                  <Text selectable style={s.code}>
                    {j.diff}
                  </Text>
                )}
                {!!j.branch && (
                  <Text selectable style={s.small}>
                    Branch: {j.branch}
                  </Text>
                )}
                {j.status === "queued" && (
                  <Button
                    title="Cancel queued job"
                    disabled={busy}
                    onPress={() =>
                      run(() => request("/desktop/cancel", { id: j.id }))
                    }
                  />
                )}
              </View>
            ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.background },
  content: { padding: 18, paddingBottom: 45 },
  title: { fontSize: 30, fontWeight: "600", color: c.text, marginVertical: 15 },
  heading: { fontSize: 20, color: c.text, marginVertical: 12 },
  text: { fontSize: 15, lineHeight: 23, color: c.text },
  small: { fontSize: 12, lineHeight: 19, color: c.muted, marginVertical: 7 },
  card: {
    backgroundColor: c.surface,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 15,
    padding: 17,
    marginVertical: 10,
  },
  input: {
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 8,
    padding: 12,
    color: c.text,
    marginBottom: 10,
  },
  button: {
    padding: 13,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: c.cyan,
    marginVertical: 6,
  },
  buttonText: { color: c.cyan, fontSize: 14 },
  article: {
    borderTopWidth: 1,
    borderColor: c.border,
    paddingVertical: 12,
    marginTop: 10,
  },
  error: { color: "#ffaaa0", padding: 10 },
  code: { color: c.text, fontSize: 11, fontFamily: "monospace" },
});
