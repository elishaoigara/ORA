import { enableAppLock, disableAppLock } from "./app-lock";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Alert,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect } from "expo-router";
import * as Speech from "expo-speech";
import * as Location from "expo-location";
import * as Battery from "expo-battery";
import * as Calendar from "expo-calendar/legacy";
import * as DocumentPicker from "expo-document-picker";
import * as Contacts from "expo-contacts/legacy";
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import { useShareIntentContext } from "expo-share-intent";
import { useMini } from "./provider";
import { makeId, readLocal, request, writeLocal, Task, Action } from "./api";
import { enableReminders, cancelReminders } from "./reminders";
import { colors as c } from "./theme";
import NativeListener from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";

type Glyph = React.ComponentProps<typeof Ionicons>["name"];
export function Button({
  title,
  onPress,
  ghost = false,
  disabled = false,
  icon,
}: {
  title: string;
  onPress: () => void;
  ghost?: boolean;
  disabled?: boolean;
  icon?: Glyph;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[s.button, ghost && s.ghost, disabled && { opacity: 0.5 }]}
    >
      {icon && (
        <Ionicons name={icon} size={18} color={ghost ? c.cyan : c.background} />
      )}
      <Text style={[s.buttonText, ghost && { color: c.cyan }]}>{title}</Text>
    </Pressable>
  );
}
function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <Image
      source={require("../../assets/images/ora-mark.png")}
      accessibilityLabel="ORA"
      style={{ width: size, height: size, borderRadius: size / 2 }}
      resizeMode="contain"
    />
  );
}
export function Orb({ small = false }: { small?: boolean }) {
  return <BrandMark size={small ? 44 : 112} />;
}
function useClock() {
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);
  return clock;
}
function Card({ children }: { children: React.ReactNode }) {
  return <View style={s.card}>{children}</View>;
}
function Title({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
}) {
  return (
    <View style={{ marginBottom: 24 }}>
      <Text style={s.eyebrow}>{eyebrow}</Text>
      <Text style={s.title}>{title}</Text>
      {detail && <Text style={s.muted}>{detail}</Text>}
    </View>
  );
}
function useAction() {
  const [busy, setBusy] = useState(false);
  const { setError } = useMini();
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}
function Frame({ children }: { children: React.ReactNode }) {
  const m = useMini();
  if (!m.session) return <PairScreen />;
  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <Button
        title="Tools & GitHub"
        icon="construct-outline"
        onPress={() => router.push("/tools")}
      />
      <Button
        title="Projects & desktop"
        icon="folder-outline"
        onPress={() => router.push("/work")}
      />
      <View style={s.topbar}>
        <View style={s.row}>
          <BrandMark />
          <Text style={s.logo}>
            ORA <Text style={s.mini}> MINI AI</Text>
          </Text>
        </View>
        <Pressable accessibilityRole="button" onPress={m.sync}>
          <Text style={s.status}>{m.status}</Text>
        </Pressable>
      </View>
      {!!m.error && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Dismiss error"
          onPress={() => m.setError("")}
          style={s.notice}
        >
          <Text style={s.noticeText}>{m.error}</Text>
        </Pressable>
      )}
      {m.queue.length > 0 && (
        <View style={s.notice}>
          <Text style={s.noticeText}>
            {m.queue.length} changes waiting to sync.
          </Text>
          <Pressable
            onPress={() =>
              Alert.alert(
                "Discard queued changes?",
                "These changes have not reached ORA.",
                [
                  { text: "Keep", style: "cancel" },
                  {
                    text: "Discard",
                    style: "destructive",
                    onPress: m.clearQueue,
                  },
                ],
              )
            }
          >
            <Text style={s.link}>Discard</Text>
          </Pressable>
        </View>
      )}
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={s.content}
      >
        {children}
        <Text style={s.footer}>ORA / 02 · Built around you.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
export function PairScreen() {
  const m = useMini();
  const { busy, run } = useAction();
  const [url, setUrl] = useState(
    process.env.EXPO_PUBLIC_API_URL || "https://ora-oovf.onrender.com",
  );
  const [code, setCode] = useState("");
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[s.content, { paddingTop: 45 }]}
      >
        <View style={s.row}>
          <BrandMark />
          <Text style={s.logo}>
            ORA <Text style={s.mini}> MINI AI</Text>
          </Text>
        </View>
        <View style={{ alignItems: "center", marginVertical: 28 }}>
          <Orb />
        </View>
        <Title
          eyebrow="YOUR AI, A LITTLE CLOSER"
          title={"A mind by\nyour side."}
          detail="Your conversations, your plans, your personal AI. Connect your private workspace."
        />
        <Card>
          <Text style={s.label}>Backend address</Text>
          <TextInput
            accessibilityLabel="Backend address"
            style={s.input}
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
            keyboardType="url"
            placeholder="https://your-ora.onrender.com"
            placeholderTextColor={c.muted}
          />
          <Text style={s.label}>One-time pairing code</Text>
          <TextInput
            accessibilityLabel="Pairing code"
            style={s.input}
            value={code}
            onChangeText={setCode}
            autoCapitalize="characters"
            placeholder="From Connections on the web"
            placeholderTextColor={c.muted}
          />
          <Button
            title={busy ? "Connecting to ORA…" : "Pair my phone"}
            disabled={busy || !code || !url}
            onPress={() => run(() => m.connect(url, code))}
            icon="arrow-forward"
          />
          <Text style={s.small}>
            Generate a code in the web app. Never paste your owner key here.
            Pairing gives this phone its own revocable connection.
          </Text>
        </Card>
        {!!m.error && <Text style={s.noticeText}>{m.error}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}
function TaskRow({ task }: { task: Task }) {
  const m = useMini();
  const { busy, run } = useAction();
  return (
    <View style={s.taskRow}>
      <Pressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: task.done }}
        accessibilityLabel={task.title}
        disabled={busy}
        onPress={() =>
          run(() =>
            m.mutate("task.complete", { id: task.id, version: task.version }),
          )
        }
        style={s.check}
      >
        {task.done && <Ionicons name="checkmark" color={c.cyan} size={18} />}
      </Pressable>
      <View style={{ flex: 1 }}>
        <Text
          style={[
            s.body,
            task.done && { textDecorationLine: "line-through", color: c.muted },
          ]}
        >
          {task.title}
        </Text>
        <Text style={s.small}>
          {task.priority === 1 ? "High priority · " : ""}
          {!task.done && task.due_at && Date.parse(task.due_at) < Date.now()
            ? "Overdue · "
            : ""}
          {task.due_at
            ? new Date(task.due_at).toLocaleString()
            : "Whenever you’re ready"}
        </Text>
      </View>
      <Pressable
        onPress={() =>
          router.push({ pathname: "/edit-task", params: { id: task.id } })
        }
        accessibilityLabel="Edit task"
      >
        <Ionicons name="create-outline" color={c.cyan} size={22} />
      </Pressable>
      <Pressable
        accessibilityLabel="Delete task"
        onPress={() =>
          Alert.alert("Delete task?", task.title, [
            { text: "Keep", style: "cancel" },
            {
              text: "Delete",
              style: "destructive",
              onPress: () =>
                run(() =>
                  m.mutate("task.delete", {
                    id: task.id,
                    version: task.version,
                  }),
                ),
            },
          ])
        }
      >
        <Ionicons name="close" color={c.muted} size={18} />
      </Pressable>
    </View>
  );
}
function Proposal({ action }: { action: Action }) {
  const m = useMini();
  const { busy, run } = useAction();
  return (
    <View
      style={[s.card, { borderColor: "#514760", backgroundColor: "#1b1c2b" }]}
    >
      <Text style={[s.eyebrow, { color: c.violet }]}>
        YOUR CALL · {action.kind.toUpperCase()}
      </Text>
      <Text style={s.body}>
        {action.payload.title ||
          action.payload.text ||
          `To ${action.payload.recipient}`}
      </Text>
      {action.payload.body && (
        <Text style={s.muted}>{action.payload.body}</Text>
      )}
      {action.payload.due_at && (
        <Text style={s.small}>
          {new Date(action.payload.due_at).toLocaleString()}
        </Text>
      )}
      <View style={s.row}>
        <Button
          title="Approve"
          disabled={busy}
          onPress={() =>
            run(() => m.mutate("action.approve", { id: action.id }))
          }
        />
        <Button
          title="Dismiss"
          ghost
          disabled={busy}
          onPress={() =>
            run(() => m.mutate("action.reject", { id: action.id }))
          }
        />
      </View>
    </View>
  );
}
export function TodayScreen() {
  const m = useMini();
  const clock = useClock();
  const tasks = (m.data?.tasks || []).filter((t) => !t.done);
  const actions = (m.data?.actions || []).filter(
    (a) => a.status === "pending" && Date.parse(a.expires_at) > clock,
  );
  return (
    <Frame>
      <Button
        title={`Alert inbox · ${(m.data?.alerts || []).filter((a) => !a.read).length} unread`}
        onPress={() => router.push("/notifications")}
      />
      <Card>
        <Text style={s.heading}>Your daily briefing</Text>
        <Text style={s.body}>
          {m.data?.tasks.filter((t) => !t.done).length || 0} tasks open ·{" "}
          {m.data?.tasks.filter(
            (t) => !t.done && t.due_at && Date.parse(t.due_at) < Date.now(),
          ).length || 0}{" "}
          overdue.
        </Text>
        <Text style={s.muted}>
          Start with{" "}
          {[...(m.data?.tasks || [])]
            .filter((t) => !t.done)
            .sort((a, b) => a.priority - b.priority)[0]?.title ||
            "one thing that matters today"}
          .
        </Text>
      </Card>
      <Title
        eyebrow={new Date(clock)
          .toLocaleDateString(undefined, {
            weekday: "long",
            month: "long",
            day: "numeric",
          })
          .toUpperCase()}
        title={"Your day,\nin focus."}
        detail={`Hey ${m.data?.settings.name || "there"}. What’s on your mind?`}
      />
      <View style={s.presence}>
        <Text style={[s.eyebrow, { color: c.cyan }]}>A MIND BY YOUR SIDE</Text>
        <View style={s.presenceRow}>
          <Text style={s.presenceTitle}>
            {"Let’s make\nsomething\nof today."}
          </Text>
          <Orb />
        </View>
        <Text style={s.muted}>
          Think out loud. Turn an idea into a small next step.
        </Text>
        <Button
          title="Talk to ORA"
          onPress={() => router.push("/(tabs)/inbox")}
          icon="arrow-forward"
        />
      </View>
      <View style={s.stats}>
        {[
          [tasks.length, "On your mind"],
          [actions.length, "For review"],
          [m.data?.memories.length || 0, "Memories"],
        ].map(([n, l]) => (
          <View key={l} style={s.stat}>
            <Text style={s.statNumber}>{String(n).padStart(2, "0")}</Text>
            <Text style={s.small}>{l}</Text>
          </View>
        ))}
      </View>
      <Text style={s.heading}>A little direction</Text>
      {m.data?.suggestions.map((a, i) => (
        <Pressable
          key={a.title}
          style={s.suggestion}
          onPress={() => {
            writeLocal("draft", a.prompt).then(() =>
              router.push("/(tabs)/inbox"),
            );
          }}
        >
          <Text style={s.number}>0{i + 1}</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.body}>{a.title}</Text>
            <Text style={s.small}>{a.detail}</Text>
          </View>
          <Ionicons name="arrow-forward" color={c.cyan} size={18} />
        </Pressable>
      ))}
      <Button
        title="New task · date picker and repeats"
        onPress={() => router.push("/edit-task")}
      />
      <Text style={s.heading}>On your radar</Text>
      <Card>
        {tasks.length ? (
          tasks.slice(0, 4).map((t) => <TaskRow key={t.id} task={t} />)
        ) : (
          <Text style={s.muted}>Start with one thing that matters today.</Text>
        )}
      </Card>
      {actions.length > 0 && <Text style={s.heading}>Your call</Text>}
      {actions.map((a) => (
        <Proposal key={a.id} action={a} />
      ))}
    </Frame>
  );
}

export function TalkScreen() {
  const m = useMini();
  const clock = useClock();
  const { busy, run } = useAction();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [recording, setRecording] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const list = useRef<ScrollView>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { hasShareIntent, shareIntent, resetShareIntent } =
    useShareIntentContext();
  useFocusEffect(
    useCallback(() => {
      readLocal("draft", "").then(setDraft);
      readLocal("autoSpeak", false).then(setAutoSpeak);
      return () => {
        Speech.stop();
        if (timer.current) clearTimeout(timer.current);
        if (recorder.isRecording) recorder.stop();
        setRecording(false);
      };
    }, [recorder]),
  );
  const update = (t: string) => {
    setDraft(t);
    writeLocal("draft", t);
  };
  const speak = async (text: string) => {
    await Speech.stop();
    const voice = await readLocal("voice", "");
    Speech.speak(text.replace(/[*#`]/g, ""), {
      voice: voice || undefined,
      rate: await readLocal("voiceRate", 0.98),
    });
  };
  const send = () =>
    run(async () => {
      if (!draft.trim()) return;
      const reply = await m.ask(draft.trim());
      update("");
      if (autoSpeak) await speak(reply);
    });
  const stop = async () => {
    await recorder.stop();
    setRecording(false);
    if (timer.current) clearTimeout(timer.current);
    if (!recorder.uri) return;
    const form = new FormData();
    form.append("file", {
      uri: recorder.uri,
      name: "ora-voice.m4a",
      type: "audio/mp4",
    } as unknown as Blob);
    const result = await request<{ text: string }>("/transcribe", form);
    update(result.text);
  };
  const record = () =>
    run(async () => {
      if (recording) {
        await stop();
        return;
      }
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted)
        throw new Error("Allow microphone access to record a voice note.");
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
      timer.current = setTimeout(() => run(stop), 60000);
    });
  if (!m.session) return <PairScreen />;
  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <Button
          title="Tools & activity · review actions"
          onPress={() => router.push("/tools")}
        />
        <View style={s.talkHeader}>
          <Orb small />
          <View style={{ flex: 1 }}>
            <Text style={s.heading}>Think out loud.</Text>
            <Text style={s.small}>{m.status}</Text>
          </View>
          <Pressable
            accessibilityLabel="Stop speaking"
            onPress={() => Speech.stop()}
          >
            <Ionicons name="volume-mute-outline" color={c.muted} size={22} />
          </Pressable>
        </View>
        {!!m.error && (
          <Pressable style={s.notice} onPress={() => m.setError("")}>
            <Text style={s.noticeText}>{m.error}</Text>
          </Pressable>
        )}
        {hasShareIntent && (
          <View style={s.notice}>
            <Text style={s.eyebrow}>SHARED WITH ORA</Text>
            {!!shareIntent.files?.length && (
              <Button
                title="Attach shared file to a project"
                onPress={() => router.push("/work")}
              />
            )}
            <Text style={s.body}>
              {(shareIntent.text || shareIntent.webUrl || "").slice(0, 500)}
            </Text>
            <Button
              title="Use as a draft"
              ghost
              onPress={() => {
                update(
                  (shareIntent.text || shareIntent.webUrl || "").slice(0, 8000),
                );
                resetShareIntent();
              }}
            />
          </View>
        )}
        <ScrollView
          ref={list}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: 22, paddingBottom: 30 }}
          onContentSizeChange={() =>
            list.current?.scrollToEnd({ animated: true })
          }
        >
          {!m.data?.messages.some((message) => !message.project_id) && (
            <View style={{ paddingVertical: 35 }}>
              <Text style={s.title}>Big idea?{"\n"}Busy mind?</Text>
              <Text style={s.muted}>
                I’m here for both. Tell me what you’re working on.
              </Text>
            </View>
          )}
          {m.data?.messages
            .filter((message) => !message.project_id)
            .filter((message) =>
              message.text.toLowerCase().includes(search.toLowerCase()),
            )
            .map((message) => (
              <View
                key={message.id}
                style={[s.message, message.role === "user" && s.userMessage]}
              >
                <Text style={s.messageLabel}>
                  {message.role === "user" ? "YOU" : "ORA"}
                </Text>
                <Text selectable style={s.body}>
                  {message.text}
                </Text>
                <Text style={s.small}>{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</Text>
                {message.role === "assistant" && (
                  <Pressable
                    accessibilityLabel="Read reply aloud"
                    onPress={() => speak(message.text)}
                    style={{ paddingTop: 12 }}
                  >
                    <Ionicons
                      name="volume-medium-outline"
                      size={18}
                      color={c.muted}
                    />
                  </Pressable>
                )}
              </View>
            ))}
          {busy && (
            <View style={s.row}>
              <ActivityIndicator color={c.cyan} />
              <Text style={s.small}>ORA is working on your reply…</Text>
            </View>
          )}
          {m.data?.actions
            .filter(
              (a) => a.status === "pending" && Date.parse(a.expires_at) > clock,
            )
            .map((a) => (
              <Proposal action={a} key={a.id} />
            ))}
        </ScrollView>
        <TextInput
          style={s.input}
          value={search}
          onChangeText={setSearch}
          placeholder="Search conversation"
          placeholderTextColor={c.muted}
          accessibilityLabel="Search conversation"
        />
        <View style={s.composer}>
          <TextInput
            accessibilityLabel="Message ORA"
            multiline
            value={draft}
            onChangeText={update}
            placeholder="Tell ORA what’s on your mind…"
            placeholderTextColor={c.muted}
            style={s.composeInput}
            maxLength={8000}
          />
          <View style={s.composeControls}>
            <Text style={s.small}>
              {recording
                ? "Recording · tap to stop"
                : "Voice becomes a draft first."}
            </Text>
            <View style={s.row}>
              <Pressable
                disabled={busy}
                accessibilityLabel={
                  recording ? "Stop recording" : "Record voice note"
                }
                onPress={record}
                style={s.mic}
              >
                <Ionicons
                  name={recording ? "stop" : "mic-outline"}
                  size={24}
                  color={recording ? "#ffaaa5" : c.cyan}
                />
              </Pressable>
              <Pressable
                accessibilityLabel="Send message"
                disabled={busy || !draft.trim()}
                onPress={send}
                style={[s.send, (busy || !draft.trim()) && { opacity: 0.4 }]}
              >
                <Ionicons name="arrow-up" size={23} color={c.background} />
              </Pressable>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
export function PlanScreen() {
  const m = useMini();
  const clock = useClock();
  const { busy, run } = useAction();
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  return (
    <Frame>
      <Title
        eyebrow="SMALL STEPS, REAL PROGRESS"
        title="Make a little space."
        detail="Your plan stays with you, even when the server is asleep."
      />
      <Card>
        <Text style={s.label}>What do you want to do?</Text>
        <TextInput
          style={s.input}
          value={title}
          onChangeText={setTitle}
          placeholder="Build something that matters"
          placeholderTextColor={c.muted}
          maxLength={240}
        />
        <Text style={s.label}>Remind me at · optional local time</Text>
        <TextInput
          style={s.input}
          value={when}
          onChangeText={setWhen}
          placeholder="2026-09-08 18:30"
          placeholderTextColor={c.muted}
        />
        <Text style={s.small}>
          You can also ask ORA naturally: “Remind me tomorrow at 6 PM.”
        </Text>
        <Button
          title="Add to my plan"
          icon="add"
          disabled={busy || !title.trim()}
          onPress={() =>
            run(async () => {
              let due_at = null;
              if (when.trim()) {
                if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(when))
                  throw new Error(
                    "Use YYYY-MM-DD HH:MM in your phone’s local time.",
                  );
                const d = new Date(when.replace(" ", "T"));
                if (!Number.isFinite(d.getTime()) || d.getTime() <= Date.now())
                  throw new Error("Choose a valid future reminder time.");
                due_at = d.toISOString();
              }
              await m.mutate("task.create", { title, due_at, priority: 2 });
              setTitle("");
              setWhen("");
            })
          }
        />
      </Card>
      <Text style={s.small}>
        Tasks save and schedule on this phone immediately, then synchronize when
        online. Android may delay delivery depending on its battery and
        notification settings.
      </Text>
      <Button
        title="New task · date picker and repeats"
        onPress={() => router.push("/edit-task")}
      />
      <Text style={s.heading}>On your radar</Text>
      <Card>
        {m.data?.tasks.length ? (
          [...m.data.tasks]
            .sort((a, b) => Number(a.done) - Number(b.done))
            .map((t) => <TaskRow key={t.id} task={t} />)
        ) : (
          <Text style={s.muted}>One small task is a good place to start.</Text>
        )}
      </Card>
      {m.data?.actions
        .filter(
          (a) => a.status === "pending" && Date.parse(a.expires_at) > clock,
        )
        .map((a) => (
          <Proposal key={a.id} action={a} />
        ))}
    </Frame>
  );
}
export function MemoryScreen() {
  const m = useMini();
  const { busy, run } = useAction();
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  return (
    <Frame>
      <Title
        eyebrow="LESS TO HOLD IN YOUR HEAD"
        title="Your second brain."
        detail="Keep what matters. Change your mind whenever you want."
      />
      <Card>
        <Text style={s.label}>Something useful to remember</Text>
        <TextInput
          style={[s.input, { minHeight: 100, textAlignVertical: "top" }]}
          multiline
          value={text}
          onChangeText={setText}
          placeholder="My current focus is…"
          placeholderTextColor={c.muted}
          maxLength={1000}
        />
        <Button
          title="Remember this"
          disabled={busy || !text.trim()}
          onPress={() =>
            run(async () => {
              await m.mutate("memory.save", { text });
              setText("");
            })
          }
          icon="add"
        />
      </Card>
      <TextInput
        style={s.input}
        value={search}
        onChangeText={setSearch}
        placeholder="Search memories or categories"
        placeholderTextColor={c.muted}
      />
      {[...(m.data?.memories || [])]
        .filter((memory) =>
          (memory.text + " " + (memory.category || ""))
            .toLowerCase()
            .includes(search.toLowerCase()),
        )
        .sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
        .map((memory) => (
          <Card key={memory.id}>
            <Text style={s.eyebrow}>
              {memory.pinned ? "PINNED · " : ""}
              {memory.category || "GENERAL"}
            </Text>
            <Button
              title="Edit memory"
              ghost
              onPress={() =>
                router.push({
                  pathname: "/edit-memory",
                  params: { id: memory.id },
                })
              }
            />
            <Text style={[s.body, { marginVertical: 14 }]}>{memory.text}</Text>
            <Pressable
              onPress={() =>
                run(() => m.mutate("memory.delete", { id: memory.id }))
              }
            >
              <Text style={s.link}>Forget</Text>
            </Pressable>
          </Card>
        ))}
      <Text style={s.heading}>Your knowledge</Text>
      <Text style={s.muted}>
        Your documents are available to ORA on both web and phone.
      </Text>
      <Button
        title="Add a document"
        ghost
        icon="document-outline"
        disabled={busy}
        onPress={() =>
          run(async () => {
            const result = await DocumentPicker.getDocumentAsync({
              type: ["application/pdf", "text/plain", "text/markdown"],
              copyToCacheDirectory: true,
            });
            if (result.canceled) return;
            const file = result.assets[0];
            if (file.size && file.size > 2 * 1024 * 1024)
              throw new Error("Choose a document under 2 MB.");
            const body = new FormData();
            body.append("file", {
              uri: file.uri,
              name: file.name,
              type: file.mimeType || "text/plain",
            } as unknown as Blob);
            await request("/documents", body);
            await m.sync();
          })
        }
      />
      {m.data?.documents.map((d) => (
        <Card key={d.id}>
          <Text style={s.body}>{d.name}</Text>
        </Card>
      ))}
      <Text style={s.heading}>Recent phone context</Text>
      {m.data?.events.length ? (
        m.data.events.map((e) => (
          <Card key={e.id}>
            <Text style={s.eyebrow}>{e.kind.toUpperCase()}</Text>
            <Text style={s.body}>{e.text}</Text>
            <Text style={s.small}>
              {new Date(e.observed_at).toLocaleString()}
            </Text>
          </Card>
        ))
      ) : (
        <Text style={s.muted}>
          Nothing shared yet. Choose sources in Settings.
        </Text>
      )}
    </Frame>
  );
}
const sources = [
  { packageName: "com.google.android.gm", appLabel: "Gmail" },
  { packageName: "com.google.android.calendar", appLabel: "Calendar" },
  { packageName: "com.whatsapp", appLabel: "WhatsApp" },
  { packageName: "org.telegram.messenger", appLabel: "Telegram" },
];
type Readiness = {
  ai_configured: boolean;
  scheduler_configured: boolean;
  scheduler_last_completed_at: string | null;
};
function ConnectionHealth() {
  const [status, setStatus] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    setError("");
    try { setStatus(await request<Readiness>("/readiness")); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not check the connection."); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return <Card>
    <Text style={s.heading}>Connection health</Text>
    {status && <>
      <Text style={s.body}>AI: {status.ai_configured ? "Key configured" : "Needs setup"}</Text>
      <Text style={s.body}>Automation: {status.scheduler_configured ? "Credential configured" : "Needs setup"}</Text>
      <Text style={s.small}>Last completed run: {status.scheduler_last_completed_at ? new Date(status.scheduler_last_completed_at).toLocaleString() : "No completed run recorded yet"}</Text>
    </>}
    {!!error && <Text accessibilityRole="alert" style={s.noticeText}>{error}</Text>}
    <Text style={s.small}>Send a message to verify the AI connection. Scheduled local reminders work after this phone has synced; weather and routine alerts need Telegram enabled in the notification center.</Text>
    <Button title={busy ? "Checking…" : "Refresh status"} disabled={busy} ghost onPress={() => void refresh()} />
  </Card>;
}

export function SettingsScreen() {
  const m = useMini();
  const { busy, run } = useAction();
  const [voiceRate, setVoiceRate] = useState(0.98);
  const [appLock, setAppLock] = useState(false);
  const [quietStart, setQuietStart] = useState(
    String(m.data?.settings.quiet_start ?? 22),
  );
  const [quietEnd, setQuietEnd] = useState(
    String(m.data?.settings.quiet_end ?? 7),
  );
  const [voices, setVoices] = useState<Speech.Voice[]>([]);
  const [voice, setVoice] = useState("");
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [reminders, setReminders] = useState(false);
  const [daily, setDaily] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const device = m.data?.devices.find((d) => d.id === m.session?.device_id);
  useEffect(() => {
    readLocal("voiceRate", 0.98).then(setVoiceRate);
    readLocal("appLock", false).then(setAppLock);
    Speech.getAvailableVoicesAsync().then(setVoices);
    readLocal("voice", "").then(setVoice);
    readLocal("autoSpeak", false).then(setAutoSpeak);
    readLocal("reminders", false).then(setReminders);
    readLocal("dailyNudge", false).then(setDaily);
    readLocal<string[]>("sources", []).then(setSelected);
  }, []);
  const permission = async (name: string) =>
    m.mutate("device.permissions", { permission: name, enabled: true });
  const event = async (kind: string, text: string) => {
    await request("/events", {
      request_id: makeId(),
      kind,
      text,
      observed_at: new Date().toISOString(),
    });
    await m.sync();
  };
  const configure = async () => {
    if (!NativeListener)
      throw new Error(
        "Install a standalone Android build to use notification access. Expo Go cannot load the listener.",
      );
    if (!selected.length) throw new Error("Choose at least one app first.");
    if (!NativeListener.getListenerStatus().accessGranted) {
      NativeListener.openNotificationListenerSettings();
      throw new Error(
        "Enable ORA in Android notification access, return here, then enable again.",
      );
    }
    await permission("notifications");
    NativeListener.configure(
      true,
      sources
        .filter((s) => selected.includes(s.packageName))
        .map((s) => ({
          ...s,
          contentMode: "redacted" as const,
          enabled: true,
        })),
    );
    await writeLocal("sources", selected);
  };
  return (
    <Frame>
      <Title
        eyebrow="MAKE ORA YOURS"
        title={"Your\nconnections."}
        detail="Choose the voice. Choose what you share. Stay in control."
      />
      <ConnectionHealth />
      <Card>
        <Button
          title="Notifications, weather and alert inbox"
          onPress={() => router.push("/notifications")}
        />
        <Text style={s.heading}>Biometric app lock</Text>
        <Switch
          value={appLock}
          onValueChange={(v) =>
            run(async () => {
              if (v) await enableAppLock();
              else await disableAppLock();
              setAppLock(v);
            })
          }
        />
        <Text style={s.small}>
          Locks when you leave ORA. Changing enrolled biometrics may require
          pairing again.
        </Text>
        <Text style={s.heading}>Quiet hours · account timezone</Text>
        <TextInput
          value={quietStart}
          onChangeText={setQuietStart}
          keyboardType="number-pad"
          style={s.input}
          accessibilityLabel="Quiet hours start 0 to 23"
        />
        <TextInput
          value={quietEnd}
          onChangeText={setQuietEnd}
          keyboardType="number-pad"
          style={s.input}
          accessibilityLabel="Quiet hours end 0 to 23"
        />
        <Button
          title="Save quiet hours"
          onPress={() =>
            run(() =>
              m.mutate("settings.update", {
                quiet_start: Number(quietStart),
                quiet_end: Number(quietEnd),
              }),
            )
          }
        />
        <Text style={s.small}>
          Quiet hours suppress remote updates. Your explicitly timed task
          reminders still sound.
        </Text>
        <Text style={s.heading}>Voice speed · {voiceRate}×</Text>
        <View style={s.row}>
          {[0.8, 0.98, 1.15].map((rate) => (
            <Button
              key={rate}
              title={String(rate)}
              ghost
              onPress={() => {
                setVoiceRate(rate);
                void writeLocal("voiceRate", rate);
              }}
            />
          ))}
        </View>
        <Text style={s.heading}>A voice you connect with</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ marginBottom: 16 }}
        >
          {[
            {
              identifier: "",
              name: "System default",
              language: "",
              quality: Speech.VoiceQuality.Default,
            },
            ...voices,
          ].map((v) => (
            <Pressable
              key={v.identifier}
              style={[
                s.voice,
                voice === v.identifier && { borderColor: c.cyan },
              ]}
              onPress={() => {
                setVoice(v.identifier);
                writeLocal("voice", v.identifier);
              }}
            >
              <Ionicons
                name="radio-outline"
                color={voice === v.identifier ? c.cyan : c.muted}
                size={22}
              />
              <Text style={s.body}>{v.name}</Text>
              <Text style={s.small}>{v.language || "On this device"}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <Button
          title="Preview voice"
          ghost
          icon="volume-medium-outline"
          onPress={() => {
            Speech.stop();
            Speech.speak(
              "Hey. I’m ORA. Let’s make room for your next big idea.",
              { voice: voice || undefined, rate: voiceRate },
            );
          }}
        />
        <View style={s.toggle}>
          <Text style={s.body}>Read replies aloud</Text>
          <Switch
            value={autoSpeak}
            trackColor={{ true: "#306c65" }}
            thumbColor={autoSpeak ? c.cyan : c.muted}
            onValueChange={(v) => {
              setAutoSpeak(v);
              writeLocal("autoSpeak", v);
            }}
          />
        </View>
        <Text style={s.small}>
          Install more voices in Android Text-to-speech settings. Availability
          and offline support depend on your speech engine.
        </Text>
      </Card>
      <Card>
        <Text style={s.heading}>Reminders that stay with you</Text>
        <View style={s.toggle}>
          <Text style={[s.body, { flex: 1 }]}>Schedule on this phone</Text>
          <Switch
            disabled={busy}
            value={reminders}
            onValueChange={(v) =>
              run(async () => {
                if (v) await enableReminders();
                else await cancelReminders();
                setReminders(v);
                await m.sync();
              })
            }
            trackColor={{ true: "#306c65" }}
            thumbColor={reminders ? c.cyan : c.muted}
          />
        </View>
        <View style={s.toggle}>
          <Text style={s.body}>A daily planning nudge</Text>
          <Switch
            disabled={busy || !reminders}
            value={daily}
            onValueChange={(v) =>
              run(async () => {
                setDaily(v);
                await writeLocal("dailyNudge", v);
                await m.sync();
              })
            }
          />
        </View>
        <Text style={s.small}>
          Daily nudge: 7 AM in your phone’s timezone, moved outside your
          workspace quiet hours.
        </Text>
        <Text style={s.small}>
          Up to 50 upcoming reminders are scheduled here. They do not need
          Render to be awake. Open ORA after creating or changing a reminder on
          the web.
        </Text>
      </Card>
      <Card>
        <Text style={s.heading}>Phone awareness</Text>
        <View style={s.toggle}>
          <Text style={s.body}>Pause all awareness</Text>
          <Switch
            disabled={busy}
            value={device?.paused ?? false}
            onValueChange={(paused) =>
              run(async () => {
                if (paused) NativeListener?.configure(false, []);
                await m.mutate("device.pause", { paused });
              })
            }
            trackColor={{ true: "#306c65" }}
            thumbColor={device?.paused ? c.cyan : c.muted}
          />
        </View>
        <Text style={s.small}>
          Turning pause off does not silently restart notification collection.
          Enable selected apps again below.
        </Text>
        <Text style={s.subheading}>Selected notifications</Text>
        <View style={s.chips}>
          {sources.map((source) => (
            <Pressable
              key={source.packageName}
              style={[
                s.chip,
                selected.includes(source.packageName) && {
                  borderColor: c.cyan,
                },
              ]}
              onPress={() =>
                setSelected((old) =>
                  old.includes(source.packageName)
                    ? old.filter((x) => x !== source.packageName)
                    : [...old, source.packageName],
                )
              }
            >
              <Text style={s.body}>{source.appLabel}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={s.small}>
          Only selected apps. Codes, links and email addresses are redacted. A
          bounded on-phone queue syncs when ORA opens; this is not instant cloud
          monitoring.
        </Text>
        <Button
          title="Enable selected apps"
          ghost
          disabled={busy || device?.paused}
          onPress={() => run(configure)}
        />
        <Button
          title="Stop notification access"
          ghost
          disabled={busy}
          onPress={() =>
            run(async () => {
              NativeListener?.configure(false, []);
              await m.mutate("device.permissions", {
                permission: "notifications",
                enabled: false,
              });
            })
          }
        />
        <Text style={s.subheading}>Share a moment of context</Text>
        <Text style={s.small}>
          These are one-time captures, not continuous tracking. Shared context
          expires after 24 hours.
        </Text>
        <Button
          title="Share my location now"
          ghost
          disabled={busy || device?.paused}
          icon="location-outline"
          onPress={() =>
            run(async () => {
              const p = await Location.requestForegroundPermissionsAsync();
              if (!p.granted)
                throw new Error("Location permission was not granted.");
              await permission("location");
              const l = await Location.getCurrentPositionAsync({
                accuracy: Location.Accuracy.Balanced,
              });
              await event(
                "location",
                `Last observed approximate coordinates: ${l.coords.latitude.toFixed(3)}, ${l.coords.longitude.toFixed(3)} (not live location).`,
              );
            })
          }
        />
        <Button
          title="Share today’s calendar"
          ghost
          disabled={busy || device?.paused}
          icon="calendar-outline"
          onPress={() =>
            run(async () => {
              const p = await Calendar.requestCalendarPermissionsAsync();
              if (!p.granted)
                throw new Error("Calendar permission was not granted.");
              const calendars = await Calendar.getCalendarsAsync(
                Calendar.EntityTypes.EVENT,
              );
              const start = new Date();
              const end = new Date(start);
              end.setHours(23, 59, 59, 999);
              const events = await Calendar.getEventsAsync(
                calendars.map((c) => c.id),
                start,
                end,
              );
              const text =
                events
                  .slice(0, 8)
                  .map(
                    (e) =>
                      `${e.title}: ${new Date(e.startDate).toLocaleString()}`,
                  )
                  .join("; ") || "No remaining calendar events today.";
              Alert.alert("Share calendar context?", text, [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Share",
                  onPress: () =>
                    run(async () => {
                      await permission("calendar");
                      await event("calendar", text.slice(0, 1200));
                    }),
                },
              ]);
            })
          }
        />
        <Button
          title="Share battery status"
          ghost
          disabled={busy || device?.paused}
          icon="battery-half-outline"
          onPress={() =>
            run(async () => {
              await permission("health");
              const level = await Battery.getBatteryLevelAsync();
              await event(
                "health",
                level < 0
                  ? "Battery status unavailable"
                  : `Battery ${Math.round(level * 100)}%.`,
              );
            })
          }
        />
        <Button
          title="Choose a contact to share"
          ghost
          disabled={busy || device?.paused}
          icon="person-outline"
          onPress={() =>
            run(async () => {
              const contact = await Contacts.presentContactPickerAsync();
              if (!contact) return;
              const summary = `Selected contact: ${contact.name}. ${contact.phoneNumbers?.[0]?.number || ""} ${contact.emails?.[0]?.email || ""}`;
              Alert.alert("Share this contact with ORA?", summary, [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Share",
                  onPress: () =>
                    run(async () => {
                      await permission("contacts");
                      await event("contacts", summary);
                    }),
                },
              ]);
            })
          }
        />
        <Button
          title="Delete shared phone context"
          ghost
          disabled={busy}
          onPress={() => run(() => m.mutate("events.delete", {}))}
        />
      </Card>
      {m.data?.actions
        .filter((a) => a.status === "ready_to_share")
        .map((a) => (
          <Card key={a.id}>
            <Text style={s.heading}>Draft for {a.payload.recipient}</Text>
            <Text style={s.body}>{a.payload.body}</Text>
            <Button
              title="Open in a messaging app"
              onPress={() => Share.share({ message: a.payload.body || "" })}
            />
            <Text style={s.small}>
              Choose and verify the recipient before sending. ORA has not sent
              this message.
            </Text>
          </Card>
        ))}
      <Card>
        <Text style={s.heading}>Your connection</Text>
        <Text style={s.muted}>{m.session?.url}</Text>
        <Text style={s.small}>
          Web and phone share one workspace. Local drafts and voice choices stay
          on this device.
        </Text>
        <Button
          title="Sync now"
          ghost
          disabled={busy}
          onPress={() => run(m.sync)}
        />
        <Button
          title="Android app settings"
          ghost
          onPress={() => Linking.openSettings()}
        />
        <Button
          title="Disconnect this phone"
          ghost
          disabled={busy}
          onPress={() =>
            Alert.alert(
              "Disconnect this phone?",
              "This clears its saved workspace and cancels ORA reminders on this device.",
              [
                { text: "Keep", style: "cancel" },
                {
                  text: "Disconnect",
                  style: "destructive",
                  onPress: () => run(m.disconnect),
                },
              ],
            )
          }
        />
      </Card>
    </Frame>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.background },
  content: { padding: 22, paddingBottom: 35 },
  topbar: {
    paddingHorizontal: 22,
    paddingVertical: 18,
    borderBottomWidth: 1,
    borderBottomColor: c.border,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  logo: { fontSize: 24, color: c.text, fontWeight: "600", letterSpacing: 3 },
  mini: { fontSize: 10, color: c.muted, letterSpacing: 1 },
  status: { fontSize: 11, color: c.muted, maxWidth: 170, textAlign: "right" },
  eyebrow: {
    fontSize: 11,
    letterSpacing: 1.8,
    color: c.muted,
    marginBottom: 12,
  },
  title: {
    fontSize: 34,
    lineHeight: 40,
    color: c.text,
    fontWeight: "600",
    letterSpacing: -1.2,
    marginBottom: 12,
  },
  muted: { fontSize: 15, lineHeight: 24, color: c.muted, marginBottom: 12 },
  body: { fontSize: 16, lineHeight: 25, color: c.text },
  small: { fontSize: 12, lineHeight: 19, color: c.muted, marginTop: 6 },
  heading: {
    fontSize: 20,
    color: c.text,
    fontWeight: "600",
    letterSpacing: -0.5,
    marginBottom: 15,
    marginTop: 8,
  },
  subheading: {
    fontSize: 17,
    color: c.text,
    fontWeight: "600",
    marginTop: 24,
    marginBottom: 12,
  },
  card: {
    backgroundColor: c.surface,
    borderColor: c.border,
    borderWidth: 1,
    borderRadius: 20,
    padding: 21,
    marginBottom: 18,
  },
  label: { fontSize: 14, color: c.muted, marginBottom: 9 },
  input: {
    backgroundColor: c.background,
    borderColor: c.border,
    borderWidth: 1,
    borderRadius: 13,
    color: c.text,
    padding: 13,
    fontSize: 16,
    marginBottom: 18,
  },
  button: {
    backgroundColor: c.cyan,
    borderColor: c.cyan,
    borderWidth: 1,
    borderRadius: 13,
    paddingVertical: 13,
    paddingHorizontal: 18,
    flexDirection: "row",
    gap: 9,
    justifyContent: "center",
    alignItems: "center",
    marginTop: 10,
    minHeight: 46,
  },
  ghost: { backgroundColor: "transparent", borderColor: c.border },
  buttonText: { color: c.background, fontSize: 14, fontWeight: "600" },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  orb: {
    width: 132,
    height: 132,
    alignItems: "center",
    justifyContent: "center",
  },
  orbit: {
    position: "absolute",
    width: 125,
    height: 125,
    borderColor: "#87e8dc40",
    borderWidth: 1,
    borderRadius: 70,
    transform: [{ rotate: "-30deg" }, { scaleY: 0.65 }],
  },
  core: {
    width: 82,
    height: 82,
    borderRadius: 45,
    backgroundColor: "#245c68",
    borderWidth: 2,
    borderColor: "#75d4ca",
    shadowColor: c.cyan,
    shadowOpacity: 0.55,
    shadowRadius: 25,
    elevation: 8,
  },
  smallOrb: { width: 42, height: 42 },
  smallOrbit: { width: 40, height: 40 },
  smallCore: { width: 24, height: 24, borderWidth: 1 },
  presence: {
    padding: 24,
    borderWidth: 1,
    borderColor: "#414e6b",
    borderRadius: 24,
    backgroundColor: "#222b43",
    marginBottom: 25,
    overflow: "hidden",
  },
  presenceRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
  },
  presenceTitle: {
    fontSize: 30,
    lineHeight: 35,
    letterSpacing: -1,
    color: c.text,
    fontWeight: "600",
    flex: 1,
  },
  stats: {
    flexDirection: "row",
    paddingBottom: 25,
    marginBottom: 20,
    borderBottomWidth: 1,
    borderBottomColor: c.border,
  },
  stat: { flex: 1 },
  statNumber: { fontSize: 28, color: c.text, fontWeight: "400" },
  suggestion: {
    padding: 18,
    backgroundColor: c.surface,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 12,
    flexDirection: "row",
    gap: 13,
    alignItems: "center",
    marginBottom: 12,
  },
  number: {
    fontSize: 11,
    color: c.violet,
    alignSelf: "flex-start",
    marginTop: 4,
  },
  taskRow: {
    flexDirection: "row",
    gap: 13,
    alignItems: "center",
    paddingVertical: 14,
  },
  check: {
    width: 24,
    height: 24,
    borderWidth: 1,
    borderColor: "#577183",
    borderRadius: 7,
    alignItems: "center",
    justifyContent: "center",
  },
  footer: {
    fontSize: 11,
    color: "#667e91",
    textAlign: "center",
    marginTop: 32,
    letterSpacing: 1,
  },
  notice: {
    margin: 12,
    padding: 12,
    borderColor: "#706342",
    borderWidth: 1,
    backgroundColor: "#29271e",
    borderRadius: 13,
  },
  noticeText: { color: "#e6d8b6", fontSize: 14, lineHeight: 21 },
  link: { color: c.cyan, fontSize: 14, marginTop: 8 },
  talkHeader: {
    padding: 22,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: c.border,
  },
  message: { marginBottom: 20, maxWidth: "96%", backgroundColor: c.surface, borderColor: c.border, borderWidth: 1, padding: 16, borderRadius: 20, borderBottomLeftRadius: 6 },
  userMessage: {
    alignSelf: "flex-end",
    backgroundColor: "#29344e",
    borderColor: "#46587d",
    borderBottomLeftRadius: 20,
    borderBottomRightRadius: 6,
    padding: 16,
    borderRadius: 20,
    maxWidth: "90%",
  },
  messageLabel: {
    fontSize: 10,
    letterSpacing: 1.5,
    color: c.muted,
    marginBottom: 9,
  },
  composer: {
    margin: 16,
    marginTop: 0,
    borderWidth: 1,
    borderColor: "#46516c",
    borderRadius: 22,
    backgroundColor: c.surface,
    padding: 14,
  },
  composeInput: {
    fontSize: 16,
    lineHeight: 24,
    color: c.text,
    minHeight: 48,
    maxHeight: 150,
    textAlignVertical: "top",
  },
  composeControls: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 6,
  },
  mic: { padding: 8 },
  send: { backgroundColor: c.cyan, borderRadius: 13, padding: 9 },
  voice: {
    width: 155,
    padding: 16,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 12,
    marginRight: 10,
    gap: 8,
  },
  toggle: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 15,
    marginVertical: 12,
  },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 20,
    paddingVertical: 7,
    paddingHorizontal: 13,
  },
});
