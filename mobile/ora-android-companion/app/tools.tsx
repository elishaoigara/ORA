import Native from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";
import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  ScrollView,
  Linking,
  Share,
  StyleSheet,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import { request, makeId, writeLocal } from "@/lib/mini/api";
import { useMini } from "@/lib/mini/provider";
import { colors as c } from "@/lib/mini/theme";
type Tool = {
  name: string;
  title: string;
  description: string;
  connected: boolean;
  enabled: boolean;
  approval: boolean;
  fields: { name: string; label: string; required: boolean }[];
};
type Run = {
  id: string;
  tool: string;
  status: string;
  args: Record<string, any>;
  preview?: any;
  result?: any;
  error?: string;
  created: number;
  expires: number;
};
type Data = { tools: Tool[]; runs: Run[]; repositories: string[] };
function Result({ value, depth = 0 }: { value: any; depth?: number }) {
  if (value == null) return null;
  if (typeof value !== "object")
    return (
      <Text selectable style={s.text}>
        {String(value)}
      </Text>
    );
  if (depth > 6)
    return (
      <Text selectable style={s.text}>
        {JSON.stringify(value)}
      </Text>
    );
  return (
    <View style={{ gap: 8 }}>
      {Object.entries(value)
        .slice(0, 80)
        .filter(([k]) => !["node_id", "avatar_url", "gravatar_id"].includes(k))
        .map(([k, v]) => (
          <View
            key={k}
            style={{
              paddingLeft: 8,
              borderLeftWidth: 1,
              borderLeftColor: c.border,
            }}
          >
            {!Array.isArray(value) && (
              <Text style={s.label}>{k.replace(/_/g, " ")}</Text>
            )}
            {typeof v === "string" && /^https:\/\//.test(v) ? (
              <Pressable onPress={() => Linking.openURL(v)}>
                <Text style={s.link}>Open source ↗</Text>
              </Pressable>
            ) : (
              <Result value={v} depth={depth + 1} />
            )}
          </View>
        ))}
    </View>
  );
}
export default function ToolsScreen() {
  const m = useMini();
  const [data, setData] = useState<Data>({
    tools: [],
    runs: [],
    repositories: [],
  });
  const [selected, setSelected] = useState("github.overview");
  const [args, setArgs] = useState<Record<string, string>>({});
  const [repo, setRepo] = useState("");
  const [filter, setFilter] = useState("");
  const [result, setResult] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(
    async () => setData(await request<Data>("/tools")),
    [],
  );
  useFocusEffect(
    useCallback(() => {
      void refresh().catch((e) => setError(String(e)));
      const timer = setInterval(() => {
        void refresh().catch(() => {});
      }, 15000);
      return () => clearInterval(timer);
    }, [refresh]),
  );
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
      await m.sync();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const run = async (name = selected, input: Record<string, any> = args) => {
    await act(async () => {
      setResult(
        await request<Run>("/tools/run", {
          name,
          args: {
            ...input,
            ...(name.startsWith("github.") && name !== "github.repositories"
              ? { repo: input.repo || repo }
              : {}),
          },
          request_id: makeId(),
        }),
      );
    });
  };
  const button = (label: string, fn: () => unknown, disabled = false) => (
    <Pressable
      accessibilityRole="button"
      disabled={busy || disabled}
      onPress={() => {
        void fn();
      }}
      style={[s.button, (busy || disabled) && { opacity: 0.4 }]}
    >
      <Text style={s.link}>{label}</Text>
    </Pressable>
  );
  const ask = async (prompt: string) => {
    await writeLocal("draft", prompt);
    router.push("/(tabs)/inbox");
  };
  const tool = data.tools.find((t) => t.name === selected);
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: 20, gap: 16 }}
      >
        {button("‹ Back", () => router.back())}
        <Text style={s.title}>Tools & GitHub</Text>
        <Text style={s.text}>
          Live tools, reviewable actions, and a record of what ORA actually did.
        </Text>
        {!!error && <Text style={{ color: "#ffaaa5" }}>{error}</Text>}
        <View style={s.card}>
          <Text style={s.heading}>GitHub workspace</Text>
          <ScrollView horizontal>
            {data.repositories.map((r) => (
              <View key={r}>
                {button((repo === r ? "● " : "") + r, () => setRepo(r))}
              </View>
            ))}
          </ScrollView>
          {!data.repositories.length && (
            <Text style={s.text}>
              Configure your GitHub connection and allowed repositories in the
              backend.
            </Text>
          )}
          <View style={s.wrap}>
            {[
              ["github.overview", "Overview"],
              ["github.tree", "Files"],
              ["github.issues", "Issues"],
              ["github.builds", "Builds"],
            ].map(([name, label]) => (
              <View key={name}>
                {button(label, () => run(name, { repo }), !repo)}
              </View>
            ))}
          </View>
          {button(
            "Investigate this repository with ORA",
            () =>
              ask(
                `Inspect ${repo}, read its actual code and build results, and recommend the next useful engineering task. Cite paths and commit SHAs. Prepare changes only for review.`,
              ),
            !repo,
          )}
        </View>
        <TextInput
          style={s.input}
          value={filter}
          onChangeText={setFilter}
          placeholder="Find a tool"
          placeholderTextColor={c.muted}
        />
        <ScrollView horizontal>
          {data.tools
            .filter((t) =>
              (t.title + " " + t.name)
                .toLowerCase()
                .includes(filter.toLowerCase()),
            )
            .map((t) => (
              <View key={t.name}>
                {button((selected === t.name ? "● " : "") + t.title, () => {
                  setSelected(t.name);
                  setArgs({});
                })}
              </View>
            ))}
        </ScrollView>
        {tool && (
          <View style={s.card}>
            <Text style={s.heading}>{tool.title}</Text>
            <Text style={s.text}>{tool.description}</Text>
            <Text style={s.label}>
              {!tool.enabled
                ? "Disabled by owner"
                : !tool.connected
                  ? "Needs connection"
                  : tool.approval
                    ? "Review before action"
                    : "Ready"}
            </Text>
            {tool.fields
              .filter((f) => f.name !== "repo")
              .map((f) => (
                <View key={f.name}>
                  <Text style={s.label}>
                    {f.label}
                    {f.required ? "" : " (optional)"}
                  </Text>
                  <TextInput
                    multiline
                    style={s.input}
                    value={args[f.name] || ""}
                    onChangeText={(v) => setArgs({ ...args, [f.name]: v })}
                  />
                </View>
              ))}
            {button(
              tool.approval ? "Prepare for review" : "Run tool",
              () => run(),
              !tool.connected || !tool.enabled,
            )}
            {button("Work through this with ORA", () =>
              ask(
                `Help me use ${tool.title}${repo ? " for " + repo : ""}. Ask for missing details before acting.`,
              ),
            )}
          </View>
        )}
        {result && (
          <View style={s.card}>
            <Text style={s.heading}>{result.tool}</Text>
            <Text style={s.label}>{result.status.replace(/_/g, " ")}</Text>
            {!!result.error && <Text style={s.text}>{result.error}</Text>}
            {!!result.result?.handoff_url &&
              /^(https:|tel:|sms:)/.test(result.result.handoff_url) &&
              button("Open on this phone", () =>
                act(() => Linking.openURL(result.result.handoff_url)),
              )}
            {!!result.result?.native_action &&
              button("Open Android clock", () =>
                act(async () => {
                  const a = result.result.native_action;
                  if (
                    !Native?.openClockAction?.(a.kind, String(a.value), a.label)
                  )
                    throw Error(
                      "Install the new APK and a compatible clock app.",
                    );
                }),
              )}
            {!!result.result?.document_id &&
              button("Save document to phone", () =>
                act(async () => {
                  const p =
                    await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync();
                  if (!p.granted) return;
                  const uri =
                    await FileSystem.StorageAccessFramework.createFileAsync(
                      p.directoryUri,
                      (result.result.name || "ora-document.txt").replace(
                        /[^a-zA-Z0-9._-]/g,
                        "_",
                      ),
                      "text/plain",
                    );
                  await FileSystem.writeAsStringAsync(uri, result.result.text);
                }),
              )}
            {result.tool === "github.tree" && result.result?.files ? (
              <View>
                {result.result.files
                  .filter((f: any) => f.type === "blob")
                  .slice(0, 100)
                  .map((f: any) => (
                    <View key={f.path}>
                      {button(f.path, () =>
                        run("github.file", {
                          repo: result.args.repo,
                          path: f.path,
                          ref: result.result.sha,
                        }),
                      )}
                    </View>
                  ))}
                <Text style={s.label}>
                  Showing up to 100 files. Use code search for larger
                  repositories.
                </Text>
              </View>
            ) : (
              <Result value={result.result || result.preview} />
            )}
            {result.tool === "github.builds" &&
              Array.isArray(result.result) &&
              result.result.map((r: any) => (
                <View key={r.id}>
                  {button("Inspect " + r.name, () =>
                    run("github.build", {
                      repo: result.args.repo,
                      run_id: r.id,
                    }),
                  )}
                </View>
              ))}
            {result.tool === "routines.list" &&
              Array.isArray(result.result) &&
              result.result.map((r: any) => (
                <View key={r.id}>
                  {button(
                    "Disable " + r.name,
                    () =>
                      act(async () => {
                        await request("/routines/" + r.id + "/disable", {});
                        setResult(null);
                      }),
                    !r.enabled,
                  )}
                </View>
              ))}
            {button("Share result", () =>
              Share.share({
                message: JSON.stringify(
                  result.result || result.preview,
                  null,
                  2,
                ),
              }),
            )}
          </View>
        )}
        <Text style={s.heading}>Awaiting your review</Text>
        {data.runs
          .filter((r) => r.status === "awaiting_approval")
          .map((r) => (
            <View style={s.card} key={r.id}>
              <Text style={s.heading}>{r.tool}</Text>
              <Result value={r.preview} />
              {button(
                "Approve this exact action",
                () =>
                  act(async () =>
                    setResult(
                      await request<Run>("/tools/actions/" + r.id, {
                        reject: false,
                      }),
                    ),
                  ),
                r.expires * 1000 < Date.now(),
              )}
              {button("Reject", () =>
                act(async () =>
                  setResult(
                    await request<Run>("/tools/actions/" + r.id, {
                      reject: true,
                    }),
                  ),
                ),
              )}
            </View>
          ))}
        <Text style={s.heading}>Activity</Text>
        {[...data.runs].reverse().map((r) => (
          <View key={r.id}>
            {button(
              `${r.tool} · ${r.status.replace(/_/g, " ")}\n${new Date(r.created * 1000).toLocaleString()}`,
              () =>
                act(async () =>
                  setResult(await request<Run>("/tools/runs/" + r.id)),
                ),
            )}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.background },
  title: { color: c.text, fontSize: 29, fontWeight: "600" },
  heading: { color: c.cyan, fontSize: 20, fontWeight: "600" },
  text: { color: c.text, lineHeight: 23 },
  label: { color: c.muted, fontSize: 12, marginVertical: 5 },
  link: { color: c.cyan },
  card: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 12 },
  button: {
    padding: 13,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: c.border,
    margin: 3,
  },
  input: {
    color: c.text,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 8,
    padding: 12,
    minHeight: 46,
  },
  wrap: { flexDirection: "row", flexWrap: "wrap" },
});
