import { useState, useEffect, useCallback } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { CameraView, CameraType, useCameraPermissions, useMicrophonePermissions, FlashMode } from 'expo-camera';
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from 'expo-audio';
import { Colors } from '@/constants/colors';
import { uploadCameraPhoto } from '@/services/upload';

type CaptureMode = 'photo' | 'video';

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function CameraScreen() {
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [micPermission, requestMicPermission] = useMicrophonePermissions();

  const [facing, setFacing] = useState<CameraType>('back');
  const [flash, setFlash] = useState<FlashMode>('off');
  const [mode, setMode] = useState<CaptureMode>('photo');
  const [cameraReady, setCameraReady] = useState(false);

  const [isRecordingVideo, setIsRecordingVideo] = useState(false);
  const [videoTimer, setVideoTimer] = useState(0);

  // expo-audio recorder — hook manages its own lifecycle
  const [audioTimer, setAudioTimer] = useState(0);
  const [audioUri, setAudioUri] = useState<string | null>(null);

  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  // RecordingStatus (statusListener arg) has no isRecording field — use useAudioRecorderState instead
  const recorderState = useAudioRecorderState(audioRecorder);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');

  useEffect(() => {
    if (!isRecordingVideo) { setVideoTimer(0); return; }
    const id = setInterval(() => setVideoTimer((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRecordingVideo]);

  useEffect(() => {
    if (!recorderState.isRecording) { setAudioTimer(0); return; }
    const id = setInterval(() => setAudioTimer((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [recorderState.isRecording]);

  const handleBack = useCallback(() => {
    if (isRecordingVideo) {
      // cameraRef not needed — CameraView handles stop internally via its ref
    }
    if (recorderState.isRecording) {
      audioRecorder.stop().catch(() => {});
    }
    router.back();
  }, [isRecordingVideo, recorderState.isRecording, audioRecorder]);

  const toggleFlash = useCallback(() => setFlash((f) => (f === 'off' ? 'on' : 'off')), []);
  const flipCamera = useCallback(() => setFacing((f) => (f === 'back' ? 'front' : 'back')), []);

  // ── Camera ref stored as a stable ref via CameraView's own ref prop ─────────
  const [cameraRef, setCameraRef] = useState<CameraView | null>(null);

  // ── Voice recording ─────────────────────────────────────────────────────────

  const handleAudioToggle = useCallback(async () => {
    if (recorderState.isRecording) {
      // Stop → store URI locally; worker handles transcription after S3 upload
      await audioRecorder.stop();
      const uri = audioRecorder.uri;
      setAudioUri(uri || null);
    } else {
      // Start recording
      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        Alert.alert('Microphone Needed', 'Allow microphone access to record voice scope notes.');
        return;
      }

      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setAudioUri(null); // clear previous on new recording
    }
  }, [recorderState.isRecording, audioRecorder]);

  // ── Camera capture ──────────────────────────────────────────────────────────

  const handleCapture = useCallback(async () => {
    if (!cameraReady || !cameraRef || uploading) return;

    if (mode === 'photo') {
      let photo;
      try {
        photo = await cameraRef.takePictureAsync({ quality: 0.85 });
      } catch {
        Alert.alert('Capture Failed', 'Could not take photo. Please try again.');
        return;
      }
      if (!photo?.uri) return;

      try {
        setUploading(true);
        setUploadStatus('Uploading photo…');
        const { jobId } = await uploadCameraPhoto(photo.uri, 'image/jpeg', {
          audioUri: audioUri ?? undefined,
        });
        setUploadStatus('Starting analysis…');
        router.push({ pathname: '/scanning' as any, params: { captureMode: 'photo', jobId } });
      } catch (err: any) {
        Alert.alert('Upload Failed', err?.message ?? 'Could not upload photo. Check your connection.');
      } finally {
        setUploading(false);
        setUploadStatus('');
      }
    } else {
      // Video recording
      if (isRecordingVideo) {
        cameraRef.stopRecording();
        return;
      }

      if (!micPermission?.granted) {
        const { granted } = await requestMicPermission();
        if (!granted) {
          Alert.alert('Microphone Access',
            'Groundwork records your voice alongside the video for scope extraction.',
            [{ text: 'Continue Anyway' }, { text: 'Cancel', style: 'cancel' }]);
        }
      }

      setIsRecordingVideo(true);
      let videoUri: string | undefined;
      try {
        const recording = await cameraRef.recordAsync({ maxDuration: 30 });
        videoUri = recording?.uri;
      } catch {
        // stopRecording() called externally — may throw
      } finally {
        setIsRecordingVideo(false);
      }

      if (!videoUri) return;

      try {
        setUploading(true);
        setUploadStatus('Uploading video…');
        // Content-type: iOS records .mov, Android records .mp4
        const contentType = videoUri.toLowerCase().endsWith('.mov')
          ? 'video/quicktime'
          : 'video/mp4';
        const { jobId } = await uploadCameraPhoto(videoUri, contentType);
        setUploadStatus('Starting analysis…');
        router.push({ pathname: '/scanning' as any, params: { captureMode: 'video', jobId } });
      } catch (err: any) {
        Alert.alert('Upload Failed', err?.message ?? 'Could not upload video. Try again.');
      } finally {
        setUploading(false);
        setUploadStatus('');
      }
    }
  }, [cameraReady, cameraRef, mode, isRecordingVideo, uploading, audioUri, micPermission]);

  // ── Permission gates ────────────────────────────────────────────────────────

  if (!cameraPermission) return <View style={styles.permGate} />;

  if (!cameraPermission.granted) {
    return (
      <SafeAreaView style={styles.permGate}>
        <View style={styles.permContent}>
          <Text style={styles.permIcon}>📷</Text>
          <Text style={styles.permTitle}>Camera Access Needed</Text>
          <Text style={styles.permBody}>
            Groundwork uses your camera to analyze rooms and generate estimates.
          </Text>
          <Pressable style={styles.permButton} onPress={requestCameraPermission}>
            <Text style={styles.permButtonText}>Allow Camera Access</Text>
          </Pressable>
          <Pressable onPress={() => router.back()}>
            <Text style={styles.permBack}>Go back</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const audioButtonBusy = uploading;

  return (
    <View style={styles.container}>
      <CameraView
        ref={setCameraRef}
        style={StyleSheet.absoluteFill}
        facing={facing}
        flash={flash}
        mode={mode === 'video' ? 'video' : 'picture'}
        onCameraReady={() => setCameraReady(true)}
      />

      {/* Upload overlay */}
      {uploading && (
        <View style={styles.uploadOverlay}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.uploadOverlayText}>{uploadStatus}</Text>
        </View>
      )}

      {/* Top bar */}
      <SafeAreaView style={styles.topBar} edges={['top']}>
        <Pressable style={styles.topBtn} onPress={handleBack} hitSlop={12} disabled={uploading}>
          <Text style={styles.topBtnText}>✕</Text>
        </Pressable>

        {(isRecordingVideo || recorderState.isRecording) && (
          <View style={styles.recordingPill}>
            <View style={[styles.recDot, isRecordingVideo && styles.recDotRed]} />
            <Text style={styles.recTimer}>
              {isRecordingVideo ? formatTime(videoTimer) : `🎙 ${formatTime(audioTimer)}`}
            </Text>
          </View>
        )}

        <Pressable style={styles.topBtn} onPress={toggleFlash} hitSlop={12} disabled={uploading}>
          <Text style={styles.topBtnText}>⚡</Text>
          {flash === 'off' && <View style={styles.flashOff} />}
        </Pressable>
      </SafeAreaView>

      {/* Bottom controls */}
      <SafeAreaView style={styles.bottomOverlay} edges={['bottom']}>
        <View style={styles.modeRow}>
          {(['photo', 'video'] as CaptureMode[]).map((m) => (
            <Pressable
              key={m}
              style={[styles.modeTab, mode === m && styles.modeTabActive]}
              onPress={() => !isRecordingVideo && !uploading && setMode(m)}
            >
              <Text style={[styles.modeTabText, mode === m && styles.modeTabTextActive]}>
                {m === 'photo' ? 'PHOTO' : 'VIDEO'}
              </Text>
            </Pressable>
          ))}
        </View>

        {mode === 'video' && !isRecordingVideo && (
          <Text style={styles.hint}>15–30 sec walkthrough · speak while recording</Text>
        )}
        {mode === 'photo' && !isRecordingVideo && !recorderState.isRecording && !audioUri && (
          <Text style={styles.hint}>Record a voice note first, then capture the room</Text>
        )}
        {mode === 'photo' && !!audioUri && !recorderState.isRecording && (
          <Text style={styles.hintGreen}>Voice note ready · now capture the room</Text>
        )}

        <View style={styles.controlsRow}>
          {/* Voice button */}
          <Pressable
            style={[
              styles.sideBtn,
              recorderState.isRecording && styles.sideBtnRecording,
              !!audioUri && !recorderState.isRecording && styles.sideBtnDone,
            ]}
            onPress={handleAudioToggle}
            disabled={audioButtonBusy || isRecordingVideo}
          >
            <Text style={styles.sideBtnIcon}>
              {recorderState.isRecording ? '⏹️' : audioUri ? '✅' : '🎙️'}
            </Text>
            <Text style={styles.sideBtnLabel}>
              {recorderState.isRecording ? 'Stop' : audioUri ? 'Re-record' : 'Voice'}
            </Text>
          </Pressable>

          {/* Capture button */}
          <Pressable
            style={[
              styles.captureBtn,
              isRecordingVideo && styles.captureBtnRecording,
              (!cameraReady || uploading) && styles.captureBtnDisabled,
            ]}
            onPress={handleCapture}
            disabled={!cameraReady || uploading}
          >
            {uploading ? (
              <ActivityIndicator color={Colors.white} />
            ) : isRecordingVideo ? (
              <View style={styles.stopIcon} />
            ) : (
              <View style={[styles.captureInner, mode === 'video' && styles.captureInnerVideo]} />
            )}
          </Pressable>

          {/* Flip button */}
          <Pressable style={styles.sideBtn} onPress={flipCamera} disabled={uploading}>
            <Text style={styles.sideBtnIcon}>🔄</Text>
            <Text style={styles.sideBtnLabel}>Flip</Text>
          </Pressable>
        </View>

        {/* Live recording waveform */}
        {recorderState.isRecording && (
          <View style={styles.audioIndicator}>
            <View style={styles.audioWave}>
              {[0.4, 0.8, 1.0, 0.7, 0.5].map((h, i) => (
                <View key={i} style={[styles.audioBar, { height: 20 * h }]} />
              ))}
            </View>
            <Text style={styles.audioIndicatorText}>
              Recording voice note — tap Stop when done
            </Text>
          </View>
        )}
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },

  uploadOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.75)',
    alignItems: 'center', justifyContent: 'center', gap: 16, zIndex: 20,
  },
  uploadOverlayText: { fontSize: 16, fontWeight: '600', color: Colors.white },

  permGate: {
    flex: 1, backgroundColor: Colors.background, alignItems: 'center', justifyContent: 'center',
  },
  permContent: { alignItems: 'center', paddingHorizontal: 40, gap: 12 },
  permIcon: { fontSize: 48, marginBottom: 8 },
  permTitle: { fontSize: 22, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  permBody: { fontSize: 15, color: Colors.textMuted, textAlign: 'center', lineHeight: 22, marginBottom: 8 },
  permButton: {
    backgroundColor: Colors.primary, borderRadius: 14,
    paddingVertical: 16, paddingHorizontal: 32, width: '100%', alignItems: 'center',
  },
  permButtonText: { fontSize: 16, fontWeight: '700', color: Colors.white },
  permBack: { fontSize: 15, color: Colors.textMuted, marginTop: 4 },

  topBar: {
    position: 'absolute', top: 0, left: 0, right: 0,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12, zIndex: 10,
  },
  topBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center', justifyContent: 'center',
  },
  topBtnText: { fontSize: 18, color: Colors.white, fontWeight: '600' },
  flashOff: {
    position: 'absolute', width: 2, height: 24,
    backgroundColor: Colors.white, borderRadius: 1, transform: [{ rotate: '45deg' }],
  },
  recordingPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: 'rgba(0,0,0,0.65)', borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 8,
  },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.primary },
  recDotRed: { backgroundColor: Colors.error },
  recTimer: { fontSize: 15, fontWeight: '700', color: Colors.white, fontVariant: ['tabular-nums'] },

  bottomOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(0,0,0,0.75)', paddingTop: 20, paddingBottom: 8, gap: 12, zIndex: 10,
  },
  modeRow: {
    flexDirection: 'row', alignSelf: 'center',
    backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 10, padding: 3, gap: 2,
  },
  modeTab: { paddingHorizontal: 24, paddingVertical: 8, borderRadius: 8 },
  modeTabActive: { backgroundColor: Colors.white },
  modeTabText: { fontSize: 13, fontWeight: '700', color: 'rgba(255,255,255,0.6)', letterSpacing: 0.8 },
  modeTabTextActive: { color: Colors.background },
  hint: { fontSize: 13, color: 'rgba(255,255,255,0.5)', textAlign: 'center', paddingHorizontal: 24 },
  hintGreen: { fontSize: 13, color: 'rgba(74,222,128,0.85)', textAlign: 'center', paddingHorizontal: 24, fontWeight: '600' },

  controlsRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around',
    paddingHorizontal: 32, paddingVertical: 8,
  },
  sideBtn: { alignItems: 'center', gap: 4, width: 64, paddingVertical: 8, borderRadius: 12 },
  sideBtnRecording: { backgroundColor: 'rgba(239,68,68,0.25)' },
  sideBtnDone: { backgroundColor: 'rgba(34,197,94,0.20)' },
  sideBtnIcon: { fontSize: 26 },
  sideBtnLabel: { fontSize: 11, color: 'rgba(255,255,255,0.7)', fontWeight: '600', textAlign: 'center' },

  captureBtn: {
    width: 80, height: 80, borderRadius: 40,
    borderWidth: 4, borderColor: Colors.white,
    alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent',
  },
  captureBtnRecording: { borderColor: Colors.error },
  captureBtnDisabled: { opacity: 0.4 },
  captureInner: { width: 62, height: 62, borderRadius: 31, backgroundColor: Colors.white },
  captureInnerVideo: { backgroundColor: Colors.error },
  stopIcon: { width: 28, height: 28, borderRadius: 4, backgroundColor: Colors.error },

  audioIndicator: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: 24, marginBottom: 4,
    backgroundColor: 'rgba(239,68,68,0.15)', borderRadius: 10,
    paddingHorizontal: 14, paddingVertical: 10,
    borderWidth: 1, borderColor: 'rgba(239,68,68,0.3)',
  },
  audioWave: { flexDirection: 'row', alignItems: 'center', gap: 3, height: 20 },
  audioBar: { width: 3, backgroundColor: Colors.error, borderRadius: 2 },
  audioIndicatorText: { flex: 1, fontSize: 12, color: 'rgba(255,255,255,0.7)' },
});
