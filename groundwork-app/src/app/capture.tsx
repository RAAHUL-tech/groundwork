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
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, PrimaryButton } from '@/components';
import { uploadLibraryAssets } from '@/services/upload';

type PickedAsset = ImagePicker.ImagePickerAsset;

const MAX_PHOTOS = 5;
const MAX_VIDEOS = 1;

// ─── Option card ──────────────────────────────────────────────────────────────
function OptionCard({
  icon,
  title,
  description,
  badge,
  onPress,
  active = false,
  delay = 0,
}: {
  icon: string;
  title: string;
  description: string;
  badge?: string;
  onPress: () => void;
  active?: boolean;
  delay?: number;
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
            <Text style={[styles.optionTitle, active && styles.optionTitleActive]}>
              {title}
            </Text>
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
  assets,
  onAdd,
  onRemove,
}: {
  assets: PickedAsset[];
  onAdd: () => void;
  onRemove: (uri: string) => void;
}) {
  return (
    <Animated.View entering={FadeIn.duration(300)} style={styles.thumbnailWrap}>
      <View style={styles.thumbnailHeader}>
        <SectionLabel style={{ color: Colors.primary, marginBottom: 0 }}>
          {`Selected · ${assets.length} item${assets.length !== 1 ? 's' : ''}`}
        </SectionLabel>
        <Pressable onPress={onAdd} hitSlop={8}>
          <Text style={styles.thumbnailAddText}>+ Add more</Text>
        </Pressable>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.thumbnailScroll}
      >
        {assets.map((asset, i) => (
          <Animated.View
            key={asset.uri}
            entering={FadeInRight.delay(i * 60).duration(250).springify()}
          >
            <Pressable style={styles.thumbnail} onLongPress={() => onRemove(asset.uri)}>
              <Image source={{ uri: asset.uri }} style={styles.thumbnailImage} />
              {asset.type === 'video' && (
                <View style={styles.thumbnailVideoTag}>
                  <Text style={styles.thumbnailVideoText}>▶</Text>
                </View>
              )}
              <Pressable
                style={styles.thumbnailRemove}
                onPress={() => onRemove(asset.uri)}
                hitSlop={4}
              >
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

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function CaptureScreen() {
  const [selectedAssets, setSelectedAssets] = useState<PickedAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');

  const openLibrary = useCallback(async () => {
    // PHPickerViewController (iOS 14+) handles privacy internally — no permission request needed.
    // Calling requestMediaLibraryPermissionsAsync() crashes if NSPhotoLibraryUsageDescription
    // is absent from Info.plist; skipping it entirely avoids that native crash.

    // Calculate remaining slots based on what's already selected
    const existingPhotos = selectedAssets.filter((a) => a.type !== 'video').length;
    const existingVideos = selectedAssets.filter((a) => a.type === 'video').length;
    const remainingPhotos = MAX_PHOTOS - existingPhotos;
    const remainingVideos = MAX_VIDEOS - existingVideos;

    if (remainingPhotos <= 0 && remainingVideos <= 0) {
      Alert.alert(
        'Limit Reached',
        `You've already selected the maximum (${MAX_PHOTOS} photos, ${MAX_VIDEOS} video).`
      );
      return;
    }

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images', 'videos'],
        allowsMultipleSelection: true,
        selectionLimit: remainingPhotos + remainingVideos,
        // No quality/compression — avoids video transcoding crash on physical device
        exif: false,
      });

      if (result.canceled || result.assets.length === 0) return;

      // Enforce per-type limits from the new selection
      const newPhotos = result.assets.filter((a) => a.type !== 'video');
      const newVideos = result.assets.filter((a) => a.type === 'video');
      const photosToAdd = newPhotos.slice(0, remainingPhotos);
      const videosToAdd = newVideos.slice(0, remainingVideos);
      const toAdd = [...photosToAdd, ...videosToAdd];

      if (toAdd.length < result.assets.length) {
        Alert.alert(
          'Some Items Skipped',
          `Only ${toAdd.length} of ${result.assets.length} selected items were added (max ${MAX_PHOTOS} photos, ${MAX_VIDEOS} video).`
        );
      }

      setSelectedAssets((prev) => {
        const existing = new Set(prev.map((a) => a.uri));
        const fresh = toAdd.filter((a) => !existing.has(a.uri));
        return [...prev, ...fresh];
      });
    } catch (err: any) {
      Alert.alert('Could Not Open Library', err?.message ?? 'Please try again.');
    }
  }, [selectedAssets]);

  const removeAsset = useCallback((uri: string) => {
    setSelectedAssets((prev) => prev.filter((a) => a.uri !== uri));
  }, []);

  const handleAnalyzeLibrary = useCallback(async () => {
    if (selectedAssets.length === 0 || uploading) return;

    try {
      setUploading(true);
      setUploadProgress(`Uploading ${selectedAssets.length} file${selectedAssets.length !== 1 ? 's' : ''}…`);

      const { jobId } = await uploadLibraryAssets(selectedAssets);

      setUploadProgress('Starting analysis…');
      router.push({
        pathname: '/scanning' as any,
        params: { captureMode: 'library', jobId },
      });
    } catch (err: any) {
      Alert.alert(
        'Upload Failed',
        err?.message ?? 'Could not upload files. Check your connection and try again.'
      );
    } finally {
      setUploading(false);
      setUploadProgress('');
    }
  }, [selectedAssets, uploading]);

  const handleLiveCapture = useCallback(() => {
    router.push('/camera');
  }, []);

  const canAnalyze = selectedAssets.length > 0;

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header — custom two-line variant */}
        <Animated.View entering={FadeIn.duration(300)} style={styles.header}>
          <ScreenHeader
            title="New Estimate"
            onBack={() => router.back()}
          />
          <Text style={styles.headerSub}>Choose how to capture the room</Text>
        </Animated.View>

        {/* Live capture option */}
        <OptionCard
          icon="📷"
          title="Live Capture"
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

        {/* Upload option */}
        <OptionCard
          icon="🖼️"
          title="Upload from Library"
          description={`Pick photos or a video from your camera roll. Up to ${MAX_PHOTOS} photos and ${MAX_VIDEOS} video.`}
          onPress={openLibrary}
          active={selectedAssets.length > 0}
          badge={selectedAssets.length > 0 ? `${selectedAssets.length} selected` : undefined}
          delay={200}
        />

        {/* Thumbnail strip */}
        {selectedAssets.length > 0 && (
          <ThumbnailStrip
            assets={selectedAssets}
            onAdd={openLibrary}
            onRemove={removeAsset}
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
              { icon: '🎙️', tip: 'Add a voice note after capture to describe scope' },
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

  // Header
  header: { gap: 2 },
  headerSub: { fontSize: 12, color: Colors.textMuted, paddingLeft: 52 },

  // Option cards
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
  optionBadge: {
    backgroundColor: Colors.primary, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  optionBadgeText: { fontSize: 11, fontWeight: '700', color: Colors.white },
  optionChevron: { fontSize: 24, color: Colors.textSubtle, fontWeight: '300' },
  optionChevronActive: { color: Colors.primary },

  // OR divider
  orRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  orLine: { flex: 1, height: 1, backgroundColor: Colors.border },
  orText: { fontSize: 12, fontWeight: '700', color: Colors.textSubtle, letterSpacing: 1 },

  // Thumbnail strip
  thumbnailWrap: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.primary + '55',
    padding: 14, gap: 10,
  },
  thumbnailHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  thumbnailAddText: { fontSize: 13, fontWeight: '600', color: Colors.primary },
  thumbnailScroll: { gap: 8, paddingVertical: 2 },
  thumbnail: {
    width: 72, height: 72, borderRadius: 10, overflow: 'hidden',
    backgroundColor: Colors.surfaceRaised,
  },
  thumbnailImage: { width: '100%', height: '100%' },
  thumbnailVideoTag: {
    position: 'absolute', bottom: 4, left: 4,
    backgroundColor: 'rgba(0,0,0,0.65)',
    borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2,
  },
  thumbnailVideoText: { fontSize: 10, color: Colors.white },
  thumbnailRemove: {
    position: 'absolute', top: 3, right: 3,
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: 'rgba(0,0,0,0.7)',
    alignItems: 'center', justifyContent: 'center',
  },
  thumbnailRemoveText: { fontSize: 9, color: Colors.white, fontWeight: '700' },
  thumbnailHint: { fontSize: 11, color: Colors.textSubtle, textAlign: 'center' },

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
  uploadingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    justifyContent: 'center', paddingVertical: 18,
  },
  uploadingText: { fontSize: 15, fontWeight: '600', color: Colors.textMuted },
});
