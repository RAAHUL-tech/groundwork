import { useEffect, useState, useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { LogoMark, EmptyState, SectionLabel, PrimaryButton } from '@/components';
import { groundworkApi, type RecentEstimate } from '@/services/api';
import { setEstimateResult, setEstimateJobId } from '@/services/estimateStore';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtTotal(n: number | null) {
  if (!n) return '—';
  return '$' + Math.round(n).toLocaleString();
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function roomLabel(est: RecentEstimate) {
  if (est.room_label) return est.room_label;
  if (est.room_type) return est.room_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return 'Room';
}

function confidenceColor(score: number | null) {
  if (!score) return Colors.textSubtle;
  if (score >= 0.85) return Colors.success;
  if (score >= 0.65) return Colors.warning;
  return Colors.error;
}

// ─── Estimate card ────────────────────────────────────────────────────────────

function EstimateCard({ est, index, onPress }: { est: RecentEstimate; index: number; onPress: () => void }) {
  const confScore = est.confidence_score ?? 0;
  const confColor = confidenceColor(confScore);
  const label = roomLabel(est);

  return (
    <Animated.View entering={FadeInDown.delay(index * 60).duration(350).springify()}>
      <Pressable
        style={({ pressed }) => [styles.estimateCard, pressed && styles.estimateCardPressed]}
        onPress={onPress}
      >
        <View style={styles.estimateCardLeft}>
          <Text style={styles.estimateRoom}>{label} Remodel</Text>
          {!!est.scope_narrative && (
            <Text style={styles.estimateScope} numberOfLines={1}>{est.scope_narrative}</Text>
          )}
          <View style={styles.estimateMeta}>
            <Text style={styles.estimateDate}>{fmtDate(est.created_at)}</Text>
            {!!est.tier && (
              <View style={styles.tierDot}>
                <Text style={styles.tierText}>{est.tier.charAt(0).toUpperCase() + est.tier.slice(1)}</Text>
              </View>
            )}
          </View>
        </View>
        <View style={styles.estimateCardRight}>
          <Text style={styles.estimateTotal}>{fmtTotal(est.total_estimate)}</Text>
          {confScore > 0 && (
            <View style={[styles.confidenceBadge, { backgroundColor: confColor + '20' }]}>
              <Text style={[styles.confidenceText, { color: confColor }]}>
                {Math.round(confScore * 100)}% conf.
              </Text>
            </View>
          )}
          <Text style={styles.estimateChevron}>›</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <View style={[styles.estimateCard, styles.skeletonCard]}>
      <View style={styles.estimateCardLeft}>
        <View style={[styles.skeletonLine, { width: '55%', height: 14 }]} />
        <View style={[styles.skeletonLine, { width: '80%', height: 11, marginTop: 6 }]} />
        <View style={[styles.skeletonLine, { width: '30%', height: 10, marginTop: 6 }]} />
      </View>
      <View style={styles.estimateCardRight}>
        <View style={[styles.skeletonLine, { width: 64, height: 18 }]} />
        <View style={[styles.skeletonLine, { width: 52, height: 20, marginTop: 4, borderRadius: 6 }]} />
      </View>
    </View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function HomeScreen() {
  const [estimates, setEstimates] = useState<RecentEstimate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecent = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const data = await groundworkApi.getRecentEstimates(10);
      setEstimates(data);
    } catch (err: any) {
      setError('Could not load estimates.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => { fetchRecent(); }, []);

  // Re-fetch when the tab comes back into focus (after completing an estimate)
  useFocusEffect(useCallback(() => { fetchRecent(); }, []));

  const handleCardPress = useCallback((est: RecentEstimate) => {
    if (est.raw_response) {
      setEstimateResult(est.raw_response);
    }
    if (est.celery_job_id) {
      setEstimateJobId(est.celery_job_id);
    }
    router.push('/estimate' as any);
  }, []);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => fetchRecent(true)}
            tintColor={Colors.primary}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.brandRow}>
            <LogoMark size={44} fontSize={22} />
            <View>
              <Text style={styles.brandName}>GROUNDWORK</Text>
              <Text style={styles.brandTagline}>Camera-to-Estimate™</Text>
            </View>
          </View>
        </View>

        {/* Hero */}
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>
            Walk in.{'\n'}Point.{'\n'}Estimate.
          </Text>
          <Text style={styles.heroSub}>
            AI-powered construction estimates from a single photo — in under 5 minutes.
          </Text>
        </View>

        {/* Primary CTA */}
        <PrimaryButton
          label="New Estimate"
          leftIcon="＋"
          onPress={() => router.push('/capture' as any)}
          style={styles.ctaButton}
        />
        <Text style={styles.ctaHint}>Takes a photo or 15-second walkthrough video</Text>

        {/* Divider */}
        <View style={styles.divider} />

        {/* Recent estimates */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <SectionLabel style={styles.sectionLabelSpacing}>Recent Estimates</SectionLabel>
            {estimates.length > 0 && (
              <View style={styles.countBadge}>
                <Text style={styles.countBadgeText}>{estimates.length}</Text>
              </View>
            )}
          </View>

          {loading && (
            <>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </>
          )}

          {!loading && error && (
            <View style={styles.errorRow}>
              <Text style={styles.errorText}>{error}</Text>
              <Pressable onPress={() => fetchRecent()} hitSlop={8}>
                <Text style={styles.retryText}>Retry</Text>
              </Pressable>
            </View>
          )}

          {!loading && !error && estimates.length === 0 && (
            <EmptyState
              icon="🏠"
              title="No estimates yet"
              body={'Tap "New Estimate" above to analyze your first room.'}
            />
          )}

          {!loading && !error && estimates.map((est, i) => (
            <EstimateCard
              key={est.id}
              est={est}
              index={i}
              onPress={() => handleCardPress(est)}
            />
          ))}
        </View>

        {/* Feature chips */}
        <View style={styles.featureRow}>
          {[
            { icon: '🔍', label: 'AI Detection' },
            { icon: '🎙️', label: 'Voice Scope' },
            { icon: '📄', label: 'Instant Proposal' },
          ].map(({ icon, label }) => (
            <View key={label} style={styles.featureChip}>
              <Text style={styles.featureChipIcon}>{icon}</Text>
              <Text style={styles.featureChipLabel}>{label}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 48 },

  // Header
  header: { paddingHorizontal: 24, paddingTop: 20, paddingBottom: 8 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  brandName: { fontSize: 15, fontWeight: '800', color: Colors.text, letterSpacing: 2 },
  brandTagline: { fontSize: 11, color: Colors.textMuted, letterSpacing: 0.5, marginTop: 1 },

  // Hero
  hero: { paddingHorizontal: 24, paddingTop: 36, paddingBottom: 32 },
  heroTitle: { fontSize: 48, fontWeight: '800', color: Colors.text, lineHeight: 54, letterSpacing: -1, marginBottom: 16 },
  heroSub: { fontSize: 16, color: Colors.textMuted, lineHeight: 24, maxWidth: 320 },

  // CTA
  ctaButton: { marginHorizontal: 24 },
  ctaHint: { marginHorizontal: 24, marginTop: 10, fontSize: 13, color: Colors.textSubtle, textAlign: 'center' },

  // Divider
  divider: { height: 1, backgroundColor: Colors.border, marginHorizontal: 24, marginTop: 32, marginBottom: 28 },

  // Section
  section: { paddingHorizontal: 24 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 },
  sectionLabelSpacing: { marginBottom: 0 },
  countBadge: { backgroundColor: Colors.primary, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  countBadgeText: { fontSize: 11, fontWeight: '700', color: Colors.white },

  // Estimate card
  estimateCard: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  estimateCardPressed: { opacity: 0.75 },
  estimateCardLeft: { flex: 1, gap: 3 },
  estimateRoom: { fontSize: 15, fontWeight: '700', color: Colors.text },
  estimateScope: { fontSize: 12, color: Colors.textMuted, lineHeight: 17 },
  estimateMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 },
  estimateDate: { fontSize: 12, color: Colors.textSubtle },
  tierDot: { backgroundColor: Colors.surfaceRaised, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 },
  tierText: { fontSize: 10, fontWeight: '600', color: Colors.textMuted },
  estimateCardRight: { alignItems: 'flex-end', gap: 4 },
  estimateTotal: { fontSize: 17, fontWeight: '700', color: Colors.primary },
  confidenceBadge: { borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2 },
  confidenceText: { fontSize: 11, fontWeight: '600' },
  estimateChevron: { fontSize: 18, color: Colors.textSubtle, fontWeight: '300', marginTop: 2 },

  // Skeleton
  skeletonCard: { opacity: 0.5 },
  skeletonLine: { backgroundColor: Colors.surfaceRaised, borderRadius: 4 },

  // Error
  errorRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12 },
  errorText: { fontSize: 14, color: Colors.textMuted, flex: 1 },
  retryText: { fontSize: 14, fontWeight: '600', color: Colors.primary },

  // Feature chips
  featureRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 24, marginTop: 28 },
  featureChip: {
    flex: 1, backgroundColor: Colors.surface, borderRadius: 12,
    borderWidth: 1, borderColor: Colors.border,
    paddingVertical: 12, alignItems: 'center', gap: 6,
  },
  featureChipIcon: { fontSize: 20 },
  featureChipLabel: { fontSize: 11, fontWeight: '600', color: Colors.textMuted, textAlign: 'center' },
});
