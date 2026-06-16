import { useRef, useState, useEffect, useCallback } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { CameraView, CameraType, useCameraPermissions, FlashMode } from 'expo-camera';
import { Colors } from '@/constants/colors';
// expo-av is not in Expo Go SDK 56; audio recording is mocked here and will
// be wired up when running as a development build against the real backend.

type CaptureMode = 'photo' | 'video';

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

export default function CameraScreen() {
  const cameraRef = useRef<CameraView>(null);
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();

  const [facing, setFacing] = useState<CameraType>('back');
  const [flash, setFlash] = useState<FlashMode>('off');
  const [mode, setMode] = useState<CaptureMode>('photo');

  const [isRecordingVideo, setIsRecordingVideo] = useState(false);
  const [videoTimer, setVideoTimer] = useState(0);

  const [isRecordingAudio, setIsRecordingAudio] = useState(false);
  const [audioTimer, setAudioTimer] = useState(0);

  const [cameraReady, setCameraReady] = useState(false);

  // Timer for video recording
  useEffect(() => {
    if (!isRecordingVideo) { setVideoTimer(0); return; }
    const id = setInterval(() => setVideoTimer((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRecordingVideo]);

  // Timer for audio recording
  useEffect(() => {
    if (!isRecordingAudio) { setAudioTimer(0); return; }
    const id = setInterval(() => setAudioTimer((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRecordingAudio]);

  const handleBack = useCallback(() => {
    if (isRecordingVideo) cameraRef.current?.stopRecording();
    router.back();
  }, [isRecordingVideo]);

  const toggleFlash = useCallback(() => {
    setFlash((f) => (f === 'off' ? 'on' : 'off'));
  }, []);

  const flipCamera = useCallback(() => {
    setFacing((f) => (f === 'back' ? 'front' : 'back'));
  }, []);

  const handleCapture = useCallback(async () => {
    if (!cameraReady || !cameraRef.current) return;

    if (mode === 'photo') {
      try {
        await cameraRef.current.takePictureAsync({ quality: 0.8 });
      } catch {}
      router.push({ pathname: '/scanning', params: { captureMode: 'photo' } });
    } else {
      if (isRecordingVideo) {
        cameraRef.current.stopRecording();
        setIsRecordingVideo(false);
        router.push({ pathname: '/scanning', params: { captureMode: 'video' } });
      } else {
        setIsRecordingVideo(true);
        try {
          await cameraRef.current.recordAsync({ maxDuration: 30 });
        } catch {}
        setIsRecordingVideo(false);
        router.push({ pathname: '/scanning', params: { captureMode: 'video' } });
      }
    }
  }, [cameraReady, mode, isRecordingVideo]);

  // Mocked: real recording wired up in dev build with expo-audio
  const handleAudioToggle = useCallback(() => {
    setIsRecordingAudio((prev) => !prev);
  }, []);

  // Permission gate
  if (!cameraPermission) {
    return <View style={styles.permGate} />;
  }

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

  return (
    <View style={styles.container}>
      <CameraView
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        facing={facing}
        flash={flash}
        mode={mode === 'video' ? 'video' : 'picture'}
        onCameraReady={() => setCameraReady(true)}
      />

      {/* Top bar */}
      <SafeAreaView style={styles.topBar} edges={['top']}>
        <Pressable style={styles.topBtn} onPress={handleBack} hitSlop={12}>
          <Text style={styles.topBtnText}>✕</Text>
        </Pressable>

        {/* Recording timer */}
        {(isRecordingVideo || isRecordingAudio) && (
          <View style={styles.recordingPill}>
            <View style={[styles.recDot, isRecordingVideo && styles.recDotRed]} />
            <Text style={styles.recTimer}>
              {isRecordingVideo ? formatTime(videoTimer) : `🎙 ${formatTime(audioTimer)}`}
            </Text>
          </View>
        )}

        <Pressable style={styles.topBtn} onPress={toggleFlash} hitSlop={12}>
          <Text style={styles.topBtnText}>{flash === 'off' ? '⚡' : '⚡'}</Text>
          {flash === 'off' && <View style={styles.flashOff} />}
        </Pressable>
      </SafeAreaView>

      {/* Bottom controls */}
      <SafeAreaView style={styles.bottomOverlay} edges={['bottom']}>
        {/* Mode selector */}
        <View style={styles.modeRow}>
          {(['photo', 'video'] as CaptureMode[]).map((m) => (
            <Pressable
              key={m}
              style={[styles.modeTab, mode === m && styles.modeTabActive]}
              onPress={() => !isRecordingVideo && setMode(m)}
            >
              <Text style={[styles.modeTabText, mode === m && styles.modeTabTextActive]}>
                {m === 'photo' ? 'PHOTO' : 'VIDEO'}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Hint text */}
        {mode === 'video' && !isRecordingVideo && (
          <Text style={styles.hint}>15–30 sec walkthrough for best results</Text>
        )}
        {mode === 'photo' && !isRecordingVideo && (
          <Text style={styles.hint}>Capture the full room in frame</Text>
        )}

        {/* Capture controls row */}
        <View style={styles.controlsRow}>
          {/* Voice note button */}
          <Pressable
            style={[styles.sideBtn, isRecordingAudio && styles.sideBtnActive]}
            onPress={handleAudioToggle}
          >
            <Text style={styles.sideBtnIcon}>🎙️</Text>
            <Text style={styles.sideBtnLabel}>
              {isRecordingAudio ? 'Stop' : 'Voice'}
            </Text>
          </Pressable>

          {/* Main capture button */}
          <Pressable
            style={[
              styles.captureBtn,
              isRecordingVideo && styles.captureBtnRecording,
              !cameraReady && styles.captureBtnDisabled,
            ]}
            onPress={handleCapture}
            disabled={!cameraReady}
          >
            {isRecordingVideo ? (
              <View style={styles.stopIcon} />
            ) : (
              <View style={[
                styles.captureInner,
                mode === 'video' && styles.captureInnerVideo,
              ]} />
            )}
          </Pressable>

          {/* Flip button */}
          <Pressable style={styles.sideBtn} onPress={flipCamera}>
            <Text style={styles.sideBtnIcon}>🔄</Text>
            <Text style={styles.sideBtnLabel}>Flip</Text>
          </Pressable>
        </View>

        {/* Audio note indicator */}
        {isRecordingAudio && (
          <View style={styles.audioIndicator}>
            <View style={styles.audioWave}>
              {[0.4, 0.8, 1.0, 0.7, 0.5].map((h, i) => (
                <View
                  key={i}
                  style={[styles.audioBar, { height: 20 * h }]}
                />
              ))}
            </View>
            <Text style={styles.audioIndicatorText}>
              Voice note recording — tap 🎙️ to stop
            </Text>
          </View>
        )}
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },

  // Permission gate
  permGate: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  permContent: {
    alignItems: 'center',
    paddingHorizontal: 40,
    gap: 12,
  },
  permIcon: {
    fontSize: 48,
    marginBottom: 8,
  },
  permTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: Colors.text,
    textAlign: 'center',
  },
  permBody: {
    fontSize: 15,
    color: Colors.textMuted,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 8,
  },
  permButton: {
    backgroundColor: Colors.primary,
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 32,
    width: '100%',
    alignItems: 'center',
  },
  permButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.white,
  },
  permBack: {
    fontSize: 15,
    color: Colors.textMuted,
    marginTop: 4,
  },

  // Top bar
  topBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
    zIndex: 10,
  },
  topBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  topBtnText: {
    fontSize: 18,
    color: Colors.white,
    fontWeight: '600',
  },
  flashOff: {
    position: 'absolute',
    width: 2,
    height: 24,
    backgroundColor: Colors.white,
    borderRadius: 1,
    transform: [{ rotate: '45deg' }],
  },

  // Recording pill
  recordingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0,0,0,0.65)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  recDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.primary,
  },
  recDotRed: {
    backgroundColor: Colors.error,
  },
  recTimer: {
    fontSize: 15,
    fontWeight: '700',
    color: Colors.white,
    fontVariant: ['tabular-nums'],
  },

  // Bottom overlay
  bottomOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(0,0,0,0.75)',
    paddingTop: 20,
    paddingBottom: 8,
    gap: 12,
    zIndex: 10,
  },

  // Mode selector
  modeRow: {
    flexDirection: 'row',
    alignSelf: 'center',
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: 10,
    padding: 3,
    gap: 2,
  },
  modeTab: {
    paddingHorizontal: 24,
    paddingVertical: 8,
    borderRadius: 8,
  },
  modeTabActive: {
    backgroundColor: Colors.white,
  },
  modeTabText: {
    fontSize: 13,
    fontWeight: '700',
    color: 'rgba(255,255,255,0.6)',
    letterSpacing: 0.8,
  },
  modeTabTextActive: {
    color: Colors.background,
  },

  // Hint
  hint: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.5)',
    textAlign: 'center',
    paddingHorizontal: 24,
  },

  // Controls row
  controlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: 32,
    paddingVertical: 8,
  },

  // Side buttons
  sideBtn: {
    alignItems: 'center',
    gap: 4,
    width: 64,
    paddingVertical: 8,
    borderRadius: 12,
  },
  sideBtnActive: {
    backgroundColor: 'rgba(255, 99, 71, 0.25)',
  },
  sideBtnIcon: {
    fontSize: 26,
  },
  sideBtnLabel: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.7)',
    fontWeight: '600',
  },

  // Capture button
  captureBtn: {
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 4,
    borderColor: Colors.white,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  captureBtnRecording: {
    borderColor: Colors.error,
  },
  captureBtnDisabled: {
    opacity: 0.4,
  },
  captureInner: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: Colors.white,
  },
  captureInnerVideo: {
    backgroundColor: Colors.error,
  },
  stopIcon: {
    width: 28,
    height: 28,
    borderRadius: 4,
    backgroundColor: Colors.error,
  },

  // Audio indicator
  audioIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginHorizontal: 24,
    marginBottom: 4,
    backgroundColor: 'rgba(239,68,68,0.15)',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.3)',
  },
  audioWave: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 20,
  },
  audioBar: {
    width: 3,
    backgroundColor: Colors.error,
    borderRadius: 2,
  },
  audioIndicatorText: {
    flex: 1,
    fontSize: 12,
    color: 'rgba(255,255,255,0.7)',
  },
});
