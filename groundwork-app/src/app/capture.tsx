import { useState, useCallback } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  Image,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import Animated, { FadeIn, FadeInDown, FadeInRight } from 'react-native-reanimated';
import {
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from 'expo-audio';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, PrimaryButton } from '@/components';
import { uploadLibraryAssets } from '@/services/upload';

type PickedAsset = ImagePicker.ImagePickerAsset;

const MAX_PHOTOS = 5;
// Only 1 video allowed; kept separate from photo picker to avoid PHPickerViewController crash.

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

// ─── Option card ──────────────────────────────────────────────────────────────
function OptionCard({
  icon, title, description, badge, onPress, active = false, delay = 0,
}: {
  icon: string; title: string; description: string; badge?: string;
  onPress: () => void; active?: boolean; delay?: number;
}) {
  return (
    <Animated.View entering={FadeInDown.delay(delay).duration(400).springify()}>
      <Pressable
        style={({ pressed }) => [
          styles.optionCard,
          active && styles.optionCardActive,
          pressed && styles.optionCardPressed,
        ]}
        onPress={onPress}
      >
        <View style={[styles.optionIconWrap, active && styles.optionIconWrapActive]}>
          <Text style={styles.optionIcon}>{icon}</Text>
        </View>
        <View style={styles.optionTextWrap}>
          <View style={styles.optionTitleRow}>
            <Text style={[styles.optionTitle, active && styles.optionTitleActive]}>{title}</Text>
            {badge && (
              <View style={styles.optionBadge}>
                <Text style={styles.optionBadgeText}>{badge}</Text>
              </View>
            )}
          </View>
          <Text style={styles.optionDescription}>{description}</Text>
        </View>
        <Text style={[styles.optionChevron, active && styles.optionChevronActive]}>›</Text>
      </Pressable>
    </Animated.View>
  );
}

// ─── Thumbnail strip ──────────────────────────────────────────────────────────
function ThumbnailStrip({
  assets, onAddPhoto, onAddVideo, onRemove, canAddPhoto, canAddVideo,
}: {
  assets: PickedAsset[];
  onAddPhoto: () => void;
  onAddVideo: () => void;
  onRemove: (uri: string) => void;
  canAddPhoto: boolean;
  canAddVideo: boolean;
}) {
  return (
    <Animated.View entering={FadeIn.duration(300)} style={styles.thumbnailWrap}>
      <View style={styles.thumbnailHeader}>
        <SectionLabel style={{ color: Colors.primary, marginBottom: 0 }}>
          {`Selected · ${assets.length} item${assets.length !== 1 ? 's' : ''}`}
        </SectionLabel>
        <View style={styles.addMoreRow}>
          {canAddPhoto && (
            <Pressable onPress={onAddPhoto} hitSlop={8} style={styles.addMoreBtn}>
              <Text style={styles.thumbnailAddText}>＋ Photo</Text>
            </Pressable>
          )}
          {canAddVideo && (
            <Pressable onPress={onAddVideo} hitSlop={8} style={styles.addMoreBtn}>
              <Text style={styles.thumbnailAddText}>＋ Video</Text>
            </Pressable>
          )}
        </View>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.thumbnailScroll}
      >
        {assets.map((asset, i) => (
          <Animated.View key={asset.uri} entering={FadeInRight.delay(i * 60).duration(250).springify()}>
            <Pressable style={styles.thumbnail} onLongPress={() => onRemove(asset.uri)}>
              {asset.type === 'video' ? (
                // Never pass a video URI to <Image> — React Native will try to decode
                // the raw video bytes as an image, which crashes on some iOS versions.
                <View style={[styles.thumbnailImage, styles.thumbnailVideoPlaceholder]}>
                  <Text style={styles.thumbnailVideoPlaceholderIcon}>🎬</Text>
                </View>
              ) : (
                <Image source={{ uri: asset.uri }} style={styles.thumbnailImage} />
              )}
              {asset.type === 'video' && (
                <View style={styles.thumbnailVideoTag}>
                  <Text style={styles.thumbnailVideoText}>▶</Text>
                </View>
              )}
              <Pressable style={styles.thumbnailRemove} onPress={() => onRemove(asset.uri)} hitSlop={4}>
                <Text style={styles.thumbnailRemoveText}>✕</Text>
              </Pressable>
            </Pressable>
          </Animated.View>
        ))}
      </ScrollView>
      <Text style={styles.thumbnailHint}>Long-press a thumbnail to remove it</Text>
    </Animated.View>
  );
}

// ─── Voice note section ───────────────────────────────────────────────────────
function VoiceNoteCard({
  isRecording, audioUri, audioTimer, onToggle, disabled,
}: {
  isRecording: boolean; audioUri: string | null; audioTimer: number;
  onToggle: () => void; disabled?: boolean;
}) {
  return (
    <Animated.View entering={FadeInDown.delay(50).duration(350).springify()} style={styles.voiceCard}>
      <View style={styles.voiceCardHeader}>
        <SectionLabel style={{ marginBottom: 0 }}>Voice Note</SectionLabel>
        <Text style={styles.voiceCardHint}>
          {audioUri && !isRecording ? 'Ready' : 'Optional — describe the scope'}
        </Text>
      </View>

      <Pressable
        style={[
          styles.voiceBtn,
          isRecording && styles.voiceBtnRecording,
          !!audioUri && !isRecording && styles.voiceBtnDone,
        ]}
        onPress={onToggle}
        disabled={disabled}
      >
        <Text style={styles.voiceBtnIcon}>
          {isRecording ? '⏹️' : audioUri ? '✅' : '🎙️'}
        </Text>
        <View style={styles.voiceBtnText}>
          <Text style={[
            styles.voiceBtnLabel,
            isRecording && { color: Colors.error },
            (!!audioUri && !isRecording) && { color: Colors.success },
          ]}>
            {isRecording ? `Recording… ${formatTime(audioTimer)}` : audioUri ? 'Voice note recorded' : 'Tap to record'}
          </Text>
          {!isRecording && (
            <Text style={styles.voiceBtnSub}>
              {audioUri ? 'Tap to re-record' : '"Replace cabinets, quartz countertops, new floors"'}
            </Text>
          )}
        </View>
        {isRecording && (
          <View style={styles.recDotWrap}>
            <View style={styles.recDot} />
          </View>
        )}
      </Pressable>

      {isRecording && (
        <View style={styles.waveRow}>
          {[0.4, 0.7, 1.0, 0.8, 0.5, 0.9, 0.6].map((h, i) => (
            <View key={i} style={[styles.waveBar, { height: 18 * h }]} />
          ))}
          <Text style={styles.waveText}>Tap Stop when done</Text>
        </View>
      )}
    </Animated.View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function CaptureScreen() {
  const [selectedAssets, setSelectedAssets] = useState<PickedAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');

  const [audioTimer, setAudioTimer] = useState(0);
  const [audioUri, setAudioUri] = useState<string | null>(null);
  const audioRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(audioRecorder);

  const startTimer = useCallback(() => {
    setAudioTimer(0);
    const id = setInterval(() => setAudioTimer((t) => t + 1), 1000);
    return id;
  }, []);

  const handleAudioToggle = useCallback(async () => {
    if (recorderState.isRecording) {
      await audioRecorder.stop();
      setAudioUri(audioRecorder.uri || null);
    } else {
      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        Alert.alert('Microphone Needed', 'Allow microphone access to record a voice note.');
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await audioRecorder.prepareToRecordAsync();
      audioRecorder.record();
      setAudioUri(null);
      startTimer();
    }
  }, [recorderState.isRecording, audioRecorder, startTimer]);

  // ── Photos — multi-select, images only ──────────────────────────────────────
  // Keeping video OUT of this picker avoids the PHPickerViewController crash on iOS
  // that occurs when allowsMultipleSelection:true is combined with video media types.
  const openPhotoLibrary = useCallback(async () => {
    const existingPhotos = selectedAssets.filter((a) => a.type !== 'video').length;
    const remaining = MAX_PHOTOS - existingPhotos;
    if (remaining <= 0) {
      Alert.alert('Limit Reached', `You can select up to ${MAX_PHOTOS} photos.`);
      return;
    }
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],          // images ONLY — no video in this call
        allowsMultipleSelection: true,
        selectionLimit: remaining,
        exif: false,
      });
      if (result.canceled || result.assets.length === 0) return;
      setSelectedAssets((prev) => {
        const existing = new Set(prev.map((a) => a.uri));
        return [...prev, ...result.assets.filter((a) => !existing.has(a.uri))];
      });
    } catch (err: any) {
      Alert.alert('Could Not Open Photos', err?.message ?? 'Please try again.');
    }
  }, [selectedAssets]);

  // ── Video — library picker ───────────────────────────────────────────────────
  // PHPickerViewController has two code paths for video:
  //   fast path  (videoExportPreset=passthrough): uses PHAssetResourceManager.writeData — crashes on this iOS build
  //   slow path  (any other preset): uses loadFileRepresentation + AVAssetExportSession — stable
  // Setting LowQuality forces the slow (transcoding) path and avoids the crash.
  const openVideoLibrary = useCallback(async () => {
    const hasVideo = selectedAssets.some((a) => a.type === 'video');
    if (hasVideo) {
      Alert.alert('Video Already Selected', 'Remove the existing video first to add a new one.');
      return;
    }
    const { granted } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!granted) {
      Alert.alert('Photo Library Access Needed', 'Allow photo library access in Settings to select a video.');
      return;
    }
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        allowsMultipleSelection: false,
        shouldDownloadFromNetwork: true,
        videoMaxDuration: 120,
        // LowQuality forces AVAssetExportSession path — avoids the PHAssetResourceManager
        // fast-path that crashes on this device/iOS version.
        videoExportPreset: ImagePicker.VideoExportPreset.LowQuality,
        exif: false,
      });
      if (result.canceled || result.assets.length === 0) return;
      const video = result.assets[0];
      setSelectedAssets((prev) => {
        const existing = new Set(prev.map((a) => a.uri));
        return existing.has(video.uri) ? prev : [...prev, video];
      });
    } catch (err: any) {
      Alert.alert('Could Not Open Videos', err?.message ?? 'Please try again.');
    }
  }, [selectedAssets]);

  const removeAsset = useCallback((uri: string) => {
    setSelectedAssets((prev) => prev.filter((a) => a.uri !== uri));
  }, []);

  const handleAnalyzeLibrary = useCallback(async () => {
    if (selectedAssets.length === 0 || uploading) return;

    if (recorderState.isRecording) {
      await audioRecorder.stop();
      setAudioUri(audioRecorder.uri || null);
    }

    try {
      setUploading(true);
      setUploadProgress(`Uploading ${selectedAssets.length} file${selectedAssets.length !== 1 ? 's' : ''}…`);

      const finalAudioUri = audioUri || (audioRecorder.uri ?? undefined);
      const { jobId } = await uploadLibraryAssets(selectedAssets, {
        audioUri: finalAudioUri ?? undefined,
      });

      setUploadProgress('Starting analysis…');
      router.push({ pathname: '/scanning' as any, params: { captureMode: 'library', jobId } });
    } catch (err: any) {
      Alert.alert('Upload Failed', err?.message ?? 'Could not upload files. Check your connection and try again.');
    } finally {
      setUploading(false);
      setUploadProgress('');
    }
  }, [selectedAssets, uploading, audioUri, audioRecorder, recorderState.isRecording]);

  const handleLiveCapture = useCallback(() => router.push('/camera'), []);

  const existingPhotos = selectedAssets.filter((a) => a.type !== 'video').length;
  const hasVideo = selectedAssets.some((a) => a.type === 'video');
  const canAddPhoto = existingPhotos < MAX_PHOTOS;
  const canAnalyze = selectedAssets.length > 0;

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <Animated.View entering={FadeIn.duration(300)} style={styles.header}>
          <ScreenHeader title="New Estimate" onBack={() => router.back()} />
          <Text style={styles.headerSub}>Choose how to capture the room</Text>
        </Animated.View>

        {/* Live capture */}
        <OptionCard
          icon="📷" title="Live Capture"
          description="Use your camera to take a photo or record a 15–30 second room walkthrough video."
          badge="Fastest"
          onPress={handleLiveCapture}
          delay={80}
        />

        {/* Divider */}
        <Animated.View entering={FadeIn.delay(160).duration(300)} style={styles.orRow}>
          <View style={styles.orLine} />
          <Text style={styles.orText}>OR</Text>
          <View style={styles.orLine} />
        </Animated.View>

        {/* Upload — two separate cards: Photos and Video */}
        <Animated.View entering={FadeInDown.delay(200).duration(400).springify()} style={styles.uploadRow}>
          {/* Photos picker */}
          <Pressable
            style={({ pressed }) => [
              styles.uploadCard,
              existingPhotos > 0 && styles.uploadCardActive,
              pressed && styles.uploadCardPressed,
            ]}
            onPress={openPhotoLibrary}
            disabled={!canAddPhoto && existingPhotos > 0}
          >
            <View style={[styles.uploadIconWrap, existingPhotos > 0 && styles.uploadIconWrapActive]}>
              <Text style={styles.uploadIcon}>🖼️</Text>
            </View>
            <Text style={[styles.uploadLabel, existingPhotos > 0 && styles.uploadLabelActive]}>
              Photos
            </Text>
            <Text style={styles.uploadSub}>
              {existingPhotos > 0 ? `${existingPhotos}/${MAX_PHOTOS}` : `Up to ${MAX_PHOTOS}`}
            </Text>
          </Pressable>

          {/* Video — library picker, forced onto slow (transcoding) path to avoid iOS crash */}
          <Pressable
            style={({ pressed }) => [
              styles.uploadCard,
              hasVideo && styles.uploadCardActive,
              pressed && styles.uploadCardPressed,
            ]}
            onPress={openVideoLibrary}
          >
            <View style={[styles.uploadIconWrap, hasVideo && styles.uploadIconWrapActive]}>
              <Text style={styles.uploadIcon}>🎬</Text>
            </View>
            <Text style={[styles.uploadLabel, hasVideo && styles.uploadLabelActive]}>
              Video
            </Text>
            <Text style={styles.uploadSub}>
              {hasVideo ? '1 selected' : 'Walkthrough'}
            </Text>
          </Pressable>
        </Animated.View>

        {/* Thumbnail strip */}
        {selectedAssets.length > 0 && (
          <ThumbnailStrip
            assets={selectedAssets}
            onAddPhoto={openPhotoLibrary}
            onAddVideo={openVideoLibrary}
            onRemove={removeAsset}
            canAddPhoto={canAddPhoto}
            canAddVideo={!hasVideo}
          />
        )}

        {/* Voice note */}
        {selectedAssets.length > 0 && (
          <VoiceNoteCard
            isRecording={recorderState.isRecording}
            audioUri={audioUri}
            audioTimer={audioTimer}
            onToggle={handleAudioToggle}
            disabled={uploading}
          />
        )}

        {/* Tips */}
        {selectedAssets.length === 0 && (
          <Animated.View entering={FadeInDown.delay(320).duration(400)} style={styles.tipsCard}>
            <SectionLabel>Tips for best results</SectionLabel>
            {[
              { icon: '💡', tip: 'Good lighting helps detect surfaces and materials' },
              { icon: '🔄', tip: 'Capture from multiple angles for full coverage' },
              { icon: '📐', tip: 'Include walls, floor, and ceiling in frame' },
              { icon: '🎙️', tip: 'Add a voice note after selecting to describe scope' },
            ].map(({ icon, tip }) => (
              <View key={tip} style={styles.tipRow}>
                <Text style={styles.tipIcon}>{icon}</Text>
                <Text style={styles.tipText}>{tip}</Text>
              </View>
            ))}
          </Animated.View>
        )}
      </ScrollView>

      {/* Sticky analyze CTA */}
      {canAnalyze && (
        <Animated.View entering={FadeInDown.duration(350)} style={styles.ctaWrap}>
          {uploading ? (
            <View style={styles.uploadingRow}>
              <ActivityIndicator color={Colors.primary} />
              <Text style={styles.uploadingText}>{uploadProgress}</Text>
            </View>
          ) : (
            <PrimaryButton
              label={`Analyze ${selectedAssets.length} Item${selectedAssets.length !== 1 ? 's' : ''}`}
              onPress={handleAnalyzeLibrary}
              disabled={uploading}
            />
          )}
        </Animated.View>
      )}
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 32, gap: 14 },

  header: { gap: 2 },
  headerSub: { fontSize: 12, color: Colors.textMuted, paddingLeft: 52 },

  optionCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: Colors.surface,
    borderRadius: 18, borderWidth: 1.5, borderColor: Colors.border,
    padding: 18,
  },
  optionCardActive: { borderColor: Colors.primary, backgroundColor: Colors.primary + '0D' },
  optionCardPressed: { opacity: 0.85 },
  optionIconWrap: {
    width: 52, height: 52, borderRadius: 14,
    backgroundColor: Colors.surfaceRaised,
    alignItems: 'center', justifyContent: 'center',
  },
  optionIconWrapActive: { backgroundColor: Colors.primary + '22' },
  optionIcon: { fontSize: 26 },
  optionTextWrap: { flex: 1, gap: 4 },
  optionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  optionTitle: { fontSize: 16, fontWeight: '700', color: Colors.text },
  optionTitleActive: { color: Colors.primary },
  optionDescription: { fontSize: 13, color: Colors.textMuted, lineHeight: 19 },
  optionBadge: { backgroundColor: Colors.primary, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  optionBadgeText: { fontSize: 11, fontWeight: '700', color: Colors.white },
  optionChevron: { fontSize: 24, color: Colors.textSubtle, fontWeight: '300' },
  optionChevronActive: { color: Colors.primary },

  orRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  orLine: { flex: 1, height: 1, backgroundColor: Colors.border },
  orText: { fontSize: 12, fontWeight: '700', color: Colors.textSubtle, letterSpacing: 1 },

  // Two upload cards side by side
  uploadRow: { flexDirection: 'row', gap: 12 },
  uploadCard: {
    flex: 1, alignItems: 'center', gap: 6,
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1.5, borderColor: Colors.border,
    paddingVertical: 20,
  },
  uploadCardActive: { borderColor: Colors.primary, backgroundColor: Colors.primary + '0D' },
  uploadCardPressed: { opacity: 0.8 },
  uploadIconWrap: {
    width: 48, height: 48, borderRadius: 14,
    backgroundColor: Colors.surfaceRaised,
    alignItems: 'center', justifyContent: 'center',
  },
  uploadIconWrapActive: { backgroundColor: Colors.primary + '22' },
  uploadIcon: { fontSize: 24 },
  uploadLabel: { fontSize: 14, fontWeight: '700', color: Colors.text },
  uploadLabelActive: { color: Colors.primary },
  uploadSub: { fontSize: 11, color: Colors.textSubtle },

  // Thumbnail strip
  thumbnailWrap: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.primary + '55',
    padding: 14, gap: 10,
  },
  thumbnailHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  addMoreRow: { flexDirection: 'row', gap: 12 },
  addMoreBtn: {},
  thumbnailAddText: { fontSize: 13, fontWeight: '600', color: Colors.primary },
  thumbnailScroll: { gap: 8, paddingVertical: 2 },
  thumbnail: { width: 72, height: 72, borderRadius: 10, overflow: 'hidden', backgroundColor: Colors.surfaceRaised },
  thumbnailImage: { width: '100%', height: '100%' },
  thumbnailVideoPlaceholder: {
    backgroundColor: Colors.surfaceRaised,
    alignItems: 'center', justifyContent: 'center',
  },
  thumbnailVideoPlaceholderIcon: { fontSize: 28 },
  thumbnailVideoTag: {
    position: 'absolute', bottom: 4, left: 4,
    backgroundColor: 'rgba(0,0,0,0.65)', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2,
  },
  thumbnailVideoText: { fontSize: 10, color: Colors.white },
  thumbnailRemove: {
    position: 'absolute', top: 3, right: 3,
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: 'rgba(0,0,0,0.7)', alignItems: 'center', justifyContent: 'center',
  },
  thumbnailRemoveText: { fontSize: 9, color: Colors.white, fontWeight: '700' },
  thumbnailHint: { fontSize: 11, color: Colors.textSubtle, textAlign: 'center' },

  // Voice note
  voiceCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    padding: 16, gap: 12,
  },
  voiceCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  voiceCardHint: { fontSize: 12, color: Colors.textSubtle },
  voiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: Colors.surfaceRaised,
    borderRadius: 14, padding: 14,
    borderWidth: 1, borderColor: Colors.border,
  },
  voiceBtnRecording: { borderColor: Colors.error, backgroundColor: Colors.error + '15' },
  voiceBtnDone:      { borderColor: Colors.success, backgroundColor: Colors.success + '15' },
  voiceBtnIcon: { fontSize: 26 },
  voiceBtnText: { flex: 1, gap: 3 },
  voiceBtnLabel: { fontSize: 15, fontWeight: '600', color: Colors.text },
  voiceBtnSub: { fontSize: 12, color: Colors.textSubtle, lineHeight: 16 },
  recDotWrap: { width: 24, alignItems: 'center' },
  recDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.error },
  waveRow: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingLeft: 4 },
  waveBar: { width: 3, backgroundColor: Colors.error + 'AA', borderRadius: 2 },
  waveText: { flex: 1, fontSize: 12, color: Colors.textMuted, marginLeft: 6 },

  // Tips
  tipsCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    padding: 16, gap: 12,
  },
  tipRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  tipIcon: { fontSize: 16, width: 24, textAlign: 'center' },
  tipText: { flex: 1, fontSize: 13, color: Colors.textMuted, lineHeight: 19 },

  // CTA
  ctaWrap: {
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },
  uploadingRow: { flexDirection: 'row', alignItems: 'center', gap: 12, justifyContent: 'center', paddingVertical: 18 },
  uploadingText: { fontSize: 15, fontWeight: '600', color: Colors.textMuted },
});
