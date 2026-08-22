import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, FlatList, Modal, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { type ShareIntent, useShareIntentContext } from "expo-share-intent";

import { ScreenContainer } from "@/components/screen-container";
import { VoiceCaptureCard } from "@/components/voice-capture-card";
import { useDevice } from "@/lib/device-provider";
import { createCapture, getCaptures, type Capture, updateCaptureStatus } from "@/lib/ora-device";

type InboxFilter = "inbox" | "saved" | "task" | "archived";

function captureIcon(kind: Capture["kind"]) {
  if (kind === "link") return "link" as const;
  if (kind === "voice_transcript") return "mic" as const;
  if (kind === "shared_file") return "attach-file" as const;
  return "notes" as const;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default function InboxScreen() {
  const { session, busy, error } = useDevice();
  const { hasShareIntent, shareIntent, resetShareIntent } = useShareIntentContext();
  const [filter, setFilter] = useState<InboxFilter>("inbox");
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [draft, setDraft] = useState("");
  const [incomingShare, setIncomingShare] = useState<ShareIntent | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    if (!session) {
      setCaptures([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setCaptures(await getCaptures(session, filter));
    } catch (err) {
      Alert.alert("Inbox unavailable", err instanceof Error ? err.message : "ORA could not load your captures.");
    } finally {
      setLoading(false);
    }
  }, [filter, session]);

  useEffect(() => {
    const timer = setTimeout(() => { void refresh(); }, 0);
    return () => clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (hasShareIntent && (shareIntent.text || shareIntent.webUrl || shareIntent.files?.length)) {
      const timer = setTimeout(() => setIncomingShare(shareIntent), 0);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [hasShareIntent, shareIntent]);

  async function saveDraft() {
    if (!session || !draft.trim()) return;
    setSaving(true);
    try {
      const value = draft.trim();
      const isLink = /^https?:\/\//i.test(value);
      await createCapture(session, {
        kind: isLink ? "link" : "text",
        title: isLink ? "Shared link" : value.slice(0, 80),
        body: value,
        metadata: isLink ? { url: value } : {},
      });
      setDraft("");
      setFilter("inbox");
      await refresh();
    } catch (err) {
      Alert.alert("Capture not saved", err instanceof Error ? err.message : "Try again after checking ORA.");
    } finally {
      setSaving(false);
    }
  }

  async function updateStatus(capture: Capture, status: Capture["status"]) {
    if (!session) return;
    try {
      await updateCaptureStatus(session, capture.id, status);
      await refresh();
    } catch (err) {
      Alert.alert("Capture not updated", err instanceof Error ? err.message : "Try again after checking ORA.");
    }
  }

  async function saveIncomingShare() {
    if (!session || !incomingShare) return;
    const text = incomingShare.webUrl || incomingShare.text || "";
    if (!text) {
      Alert.alert("Files need an import", "ORA received the share request, but this version only imports text and links. No file contents were sent.");
      return;
    }
    setSaving(true);
    try {
      const isLink = Boolean(incomingShare.webUrl) || /^https?:\/\//i.test(text);
      await createCapture(session, {
        kind: isLink ? "link" : "text",
        title: incomingShare.meta?.title || (isLink ? "Shared link" : text.slice(0, 80)),
        body: text,
        metadata: { source: "android_share_intent", has_files: Boolean(incomingShare.files?.length) },
      });
      setIncomingShare(null);
      resetShareIntent(true);
      setFilter("inbox");
      await refresh();
    } catch (err) {
      Alert.alert("Shared item not saved", err instanceof Error ? err.message : "Try again after checking ORA.");
    } finally {
      setSaving(false);
    }
  }

  function discardIncomingShare() {
    setIncomingShare(null);
    resetShareIntent(true);
  }

  const subtitle = useMemo(() => filter === "inbox" ? "Review new captures before ORA turns them into work." : filter === "saved" ? "References you chose to keep." : filter === "task" ? "Captures you deliberately turned into local ORA tasks." : "Captures you set aside.", [filter]);

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <FlatList
        data={captures}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.listContent}
        refreshing={loading}
        onRefresh={() => void refresh()}
        ListHeaderComponent={
          <View style={styles.headerStack}>
            <View><Text style={styles.eyebrow}>ORA // INBOX</Text><Text style={styles.title}>Capture, then decide.</Text><Text style={styles.subtitle}>{subtitle}</Text></View>
            <View style={styles.composer}>
              <TextInput
                value={draft}
                onChangeText={setDraft}
                placeholder="Save a thought or link…"
                placeholderTextColor="#6F8980"
                multiline
                maxLength={12000}
                style={styles.input}
              />
              <Pressable disabled={!draft.trim() || saving || busy} onPress={() => void saveDraft()} style={({ pressed }) => [styles.sendButton, (!draft.trim() || saving || busy || pressed) && styles.pressed]}>
                {saving ? <ActivityIndicator size="small" color="#08110F" /> : <MaterialIcons name="arrow-upward" color="#08110F" size={20} />}
              </Pressable>
            </View>
            <VoiceCaptureCard onSaved={refresh} />
            <View style={styles.segmentRow}>
              {(["inbox", "saved", "task", "archived"] as const).map((name) => (
                <Pressable key={name} onPress={() => setFilter(name)} style={[styles.segment, filter === name && styles.segmentActive]}>
                  <Text style={[styles.segmentText, filter === name && styles.segmentTextActive]}>{name.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        }
        renderItem={({ item }) => (
          <View style={styles.captureCard}>
            <View style={styles.captureIcon}><MaterialIcons name={captureIcon(item.kind)} color="#4CA7FF" size={20} /></View>
            <View style={styles.captureCopy}>
              <Text numberOfLines={2} style={styles.captureTitle}>{item.title}</Text>
              {item.body ? <Text numberOfLines={3} style={styles.captureBody}>{item.body}</Text> : null}
              <Text style={styles.captureTime}>{formatDate(item.created_at)}</Text>
            </View>
            {filter === "inbox" ? <View style={styles.cardActions}><Pressable onPress={() => void updateStatus(item, "saved")}><Text style={styles.saveText}>KEEP</Text></Pressable><Pressable onPress={() => void updateStatus(item, "task")}><Text style={styles.taskText}>TASK</Text></Pressable><Pressable onPress={() => void updateStatus(item, "archived")}><Text style={styles.archiveText}>ARCHIVE</Text></Pressable></View> : null}
          </View>
        )}
        ListEmptyComponent={!loading ? <View style={styles.empty}><MaterialIcons name="inbox" color="#38D996" size={28} /><Text style={styles.emptyTitle}>Nothing here yet.</Text><Text style={styles.emptyBody}>Use the capture box to save a thought or a link for ORA.</Text>{error ? <Text style={styles.errorText}>{error}</Text> : null}</View> : null}
      />
      <Modal animationType="slide" transparent visible={Boolean(incomingShare)} onRequestClose={discardIncomingShare}>
        <View style={styles.modalBackdrop}>
          <View style={styles.shareSheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.shareTitleRow}><View style={styles.shareIcon}><MaterialIcons name="ios-share" size={19} color="#00E6A7" /></View><View><Text style={styles.sheetEyebrow}>SHARED TO ORA</Text><Text style={styles.sheetTitle}>Review before saving</Text></View></View>
            <Text numberOfLines={6} style={styles.sharePreview}>{incomingShare?.webUrl || incomingShare?.text || `${incomingShare?.files?.length ?? 0} file attachment(s) selected`}</Text>
            {incomingShare?.files?.length ? <Text style={styles.fileNotice}>Files are not uploaded by this text-and-link capture. ORA will only receive the reviewed text or URL you save.</Text> : null}
            <View style={styles.sheetActions}><Pressable onPress={discardIncomingShare} style={({ pressed }) => [styles.cancelShare, pressed && styles.pressed]}><Text style={styles.cancelShareText}>DISCARD</Text></Pressable><Pressable disabled={saving || !session || !(incomingShare?.text || incomingShare?.webUrl)} onPress={() => void saveIncomingShare()} style={({ pressed }) => [styles.confirmShare, (pressed || saving || !session || !(incomingShare?.text || incomingShare?.webUrl)) && styles.pressed]}>{saving ? <ActivityIndicator color="#08110F" /> : <Text style={styles.confirmShareText}>SAVE TO INBOX</Text>}</Pressable></View>
          </View>
        </View>
      </Modal>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  listContent: { padding: 20, paddingBottom: 32, gap: 10, flexGrow: 1 },
  headerStack: { gap: 15, marginBottom: 8 },
  eyebrow: { color: "#00E6A7", fontSize: 11, fontWeight: "800", letterSpacing: 3.1 },
  title: { color: "#F2FFF9", fontSize: 29, fontWeight: "700", letterSpacing: -0.5, marginTop: 8 },
  subtitle: { color: "#95AAA3", fontSize: 14, lineHeight: 21, marginTop: 7 },
  composer: { minHeight: 84, borderWidth: 1, borderColor: "#1F5948", backgroundColor: "#12382E", borderRadius: 20, padding: 12, flexDirection: "row", gap: 8, alignItems: "flex-end" },
  input: { color: "#F2FFF9", flex: 1, minHeight: 44, maxHeight: 100, fontSize: 14, lineHeight: 20, paddingTop: 8, paddingHorizontal: 4 },
  sendButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#00E6A7", alignItems: "center", justifyContent: "center" },
  segmentRow: { flexDirection: "row", backgroundColor: "#10201C", borderRadius: 14, padding: 4, borderColor: "#1D3931", borderWidth: 1 },
  segment: { flex: 1, alignItems: "center", paddingVertical: 9, borderRadius: 10 },
  segmentActive: { backgroundColor: "#1F5948" },
  segmentText: { color: "#95AAA3", fontSize: 9, fontWeight: "800", letterSpacing: 1.1 },
  segmentTextActive: { color: "#F2FFF9" },
  captureCard: { flexDirection: "row", gap: 12, padding: 14, borderRadius: 18, backgroundColor: "#10201C", borderColor: "#1D3931", borderWidth: 1, alignItems: "flex-start" },
  captureIcon: { width: 34, height: 34, borderRadius: 12, backgroundColor: "#102D2B", alignItems: "center", justifyContent: "center" },
  captureCopy: { flex: 1, gap: 4 },
  captureTitle: { color: "#F2FFF9", fontSize: 14, fontWeight: "700" },
  captureBody: { color: "#B8D7CD", fontSize: 12, lineHeight: 17 },
  captureTime: { color: "#6F8980", fontSize: 10, marginTop: 2 },
  cardActions: { alignItems: "flex-end", gap: 12, paddingTop: 3 },
  saveText: { color: "#00E6A7", fontSize: 9, fontWeight: "800", letterSpacing: 0.8 },
  taskText: { color: "#F5B94C", fontSize: 9, fontWeight: "800", letterSpacing: 0.8 },
  archiveText: { color: "#95AAA3", fontSize: 9, fontWeight: "800", letterSpacing: 0.6 },
  empty: { flex: 1, minHeight: 240, alignItems: "center", justifyContent: "center", paddingHorizontal: 38, gap: 9 },
  emptyTitle: { color: "#F2FFF9", fontSize: 16, fontWeight: "700", marginTop: 4 },
  emptyBody: { color: "#95AAA3", fontSize: 13, textAlign: "center", lineHeight: 19 },
  errorText: { color: "#F87171", fontSize: 11, textAlign: "center", marginTop: 8 },
  modalBackdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.62)" },
  shareSheet: { borderTopLeftRadius: 28, borderTopRightRadius: 28, backgroundColor: "#10201C", borderColor: "#1D3931", borderWidth: 1, padding: 20, paddingBottom: 28, gap: 17 },
  sheetHandle: { width: 38, height: 4, borderRadius: 2, backgroundColor: "#486258", alignSelf: "center" },
  shareTitleRow: { flexDirection: "row", alignItems: "center", gap: 11 },
  shareIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: "#102D2B", alignItems: "center", justifyContent: "center" },
  sheetEyebrow: { color: "#95AAA3", fontSize: 9, fontWeight: "800", letterSpacing: 1.5 },
  sheetTitle: { color: "#F2FFF9", fontSize: 18, fontWeight: "700", marginTop: 2 },
  sharePreview: { color: "#D8EEE5", fontSize: 14, lineHeight: 21, backgroundColor: "#0B1512", borderRadius: 14, padding: 13 },
  fileNotice: { color: "#F5B94C", fontSize: 11, lineHeight: 16 },
  sheetActions: { flexDirection: "row", gap: 10 },
  cancelShare: { flex: 0.9, height: 48, alignItems: "center", justifyContent: "center", borderRadius: 14, borderColor: "#315046", borderWidth: 1 },
  cancelShareText: { color: "#B8D7CD", fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  confirmShare: { flex: 1.5, height: 48, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: "#00E6A7" },
  confirmShareText: { color: "#08110F", fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  pressed: { opacity: 0.75, transform: [{ scale: 0.97 }] },
});
