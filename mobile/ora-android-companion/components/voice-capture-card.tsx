import { useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import * as FileSystem from "expo-file-system/legacy";
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";

import { useDevice } from "@/lib/device-provider";
import { uploadVoiceCapture } from "@/lib/ora-device";

type VoiceCaptureCardProps = { onSaved?: () => Promise<void> | void };

export function VoiceCaptureCard({ onSaved }: VoiceCaptureCardProps) {
  const { session, busy } = useDevice();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const [processing, setProcessing] = useState(false);
  const [status, setStatus] = useState("Tap to record a private note.");

  async function start() {
    if (!session) {
      Alert.alert("Connect ORA first", "Pair this phone before sending a voice capture.");
      return;
    }
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        Alert.alert("Microphone not enabled", "ORA only records after you tap the microphone. You can enable microphone access in Android settings later.");
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setStatus("Recording. Tap again when you are done.");
    } catch (err) {
      Alert.alert("Voice capture unavailable", err instanceof Error ? err.message : "The recorder could not start.");
    }
  }

  async function stopAndSave() {
    if (!session) return;
    setProcessing(true);
    let uri: string | null = null;
    try {
      await recorder.stop();
      uri = recorder.uri;
      if (!uri) throw new Error("The recording file could not be found.");
      setStatus("Transcribing your note…");
      const result = await uploadVoiceCapture(session, {
        uri,
        filename: "ora-companion-note.m4a",
        mimeType: "audio/m4a",
      });
      setStatus("Transcript saved to your reviewable ORA inbox.");
      await onSaved?.();
      Alert.alert("Voice note saved", result.transcription.text);
    } catch (err) {
      const message = err instanceof Error ? err.message : "ORA could not transcribe this recording.";
      setStatus("Voice note was not saved.");
      Alert.alert("Voice capture failed", message);
    } finally {
      if (uri) {
        try {
          await FileSystem.deleteAsync(uri, { idempotent: true });
        } catch {
          // The operating system will clear a temporary recording if deletion is unavailable.
        }
      }
      setProcessing(false);
      await setAudioModeAsync({ allowsRecording: false }).catch(() => undefined);
    }
  }

  const recording = recorderState.isRecording;
  return (
    <View style={styles.card}>
      <View style={styles.copy}><Text style={styles.kicker}>PUSH-TO-TALK</Text><Text style={styles.title}>{recording ? "Listening now" : "Speak a private note"}</Text><Text style={styles.body}>{status}</Text></View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={recording ? "Stop and save voice note" : "Start voice note"}
        disabled={processing || busy}
        onPress={() => void (recording ? stopAndSave() : start())}
        style={({ pressed }) => [styles.recordButton, recording && styles.recordingButton, (pressed || processing || busy) && styles.pressed]}
      >
        {processing ? <ActivityIndicator color="#08110F" /> : <MaterialIcons name={recording ? "stop" : "mic"} size={22} color="#08110F" />}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { minHeight: 114, borderRadius: 22, padding: 16, backgroundColor: "#162742", borderColor: "#2A466C", borderWidth: 1, flexDirection: "row", alignItems: "center", gap: 14 },
  copy: { flex: 1, gap: 4 },
  kicker: { color: "#88BDFD", fontSize: 9, fontWeight: "800", letterSpacing: 1.5 },
  title: { color: "#F2F7FF", fontSize: 16, fontWeight: "700" },
  body: { color: "#B7C9E4", fontSize: 11, lineHeight: 16 },
  recordButton: { width: 50, height: 50, borderRadius: 25, backgroundColor: "#00E6A7", alignItems: "center", justifyContent: "center" },
  recordingButton: { backgroundColor: "#F5B94C" },
  pressed: { opacity: 0.78, transform: [{ scale: 0.97 }] },
});
