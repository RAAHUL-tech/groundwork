import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel } from '@/components';
import { groundworkApi, type ProjectAggregate, type ProjectRoom, type RecentEstimate } from '@/services/api';
import { setEstimateResult, setEstimateJobId } from '@/services/estimateStore';

function fmt(n: number) {
  return '$' + Math.round(n).toLocaleString();
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return `${diff}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ─── Aggregate stat row ───────────────────────────────────────────────────────

function StatRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, highlight && styles.statValueHL]}>{value}</Text>
    </View>
  );
}

// ─── Room card ────────────────────────────────────────────────────────────────

function RoomCard({
  room,
  index,
  estimateReady,
  onPress,
}: {
  room: ProjectRoom;
  index: number;
  estimateReady: boolean;
  onPress: () => void;
}) {
  return (
    <Animated.View entering={FadeInDown.delay(index * 60 + 200).duration(350).springify()}>
      <Pressable
        style={({ pressed }) => [styles.roomCard, pressed && { opacity: 0.75 }]}
        onPress={onPress}
      >
        <View style={styles.roomLeft}>
          <Text style={styles.roomLabel}>{room.room_label}</Text>
          <Text style={styles.roomDate}>{fmtDate(room.added_at)}</Text>
        </View>
        <View style={styles.roomRight}>
          <Text style={styles.roomTotal}>{fmt(room.total_estimate)}</Text>
          {estimateReady ? (
            <Text style={styles.roomChevron}>›</Text>
          ) : (
            <Text style={styles.roomNoData}>No data</Text>
          )}
        </View>
      </Pressable>
    </Animated.View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [project, setProject] = useState<ProjectAggregate | null>(null);
  const [recentEstimates, setRecentEstimates] = useState<RecentEstimate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async (isRefresh = false) => {
    if (!id) return;
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [agg, recents] = await Promise.all([
        groundworkApi.getProjectAggregate(id),
        groundworkApi.getRecentEstimates(100),
      ]);
      setProject(agg);
      setRecentEstimates(recents);
    } catch {
      setError('Could not load project.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [id]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleRoomPress = useCallback((room: ProjectRoom) => {
    const est = recentEstimates.find((e) => e.id === room.estimate_id);
    if (!est) return;
    if (est.raw_response) setEstimateResult(est.raw_response);
    if (est.celery_job_id) setEstimateJobId(est.celery_job_id);
    router.push('/estimate' as any);
  }, [recentEstimates]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ScreenHeader title="Project" onBack={() => router.back()} />
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  if (error || !project) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ScreenHeader title="Project" onBack={() => router.back()} />
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error ?? 'Project not found.'}</Text>
          <Pressable onPress={() => fetchAll()} style={styles.retryBtn}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const { aggregate, rooms } = project;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => fetchAll(true)}
            tintColor={Colors.primary}
          />
        }
      >
        <ScreenHeader title={project.name} onBack={() => router.back()} />

        {/* Client info */}
        {(project.client_name || project.client_address) && (
          <Animated.View entering={FadeInDown.delay(60).duration(350).springify()} style={styles.clientCard}>
            {!!project.client_name && (
              <Text style={styles.clientName}>👤 {project.client_name}</Text>
            )}
            {!!project.client_address && (
              <Text style={styles.clientAddress}>📍 {project.client_address}</Text>
            )}
          </Animated.View>
        )}

        {/* Aggregate totals */}
        <Animated.View entering={FadeInDown.delay(100).duration(350).springify()} style={styles.aggregateCard}>
          <SectionLabel style={{ marginBottom: 8 }}>Project Total</SectionLabel>
          <Text style={styles.grandTotal}>{fmt(aggregate.grand_total)}</Text>

          <View style={styles.divider} />

          <StatRow label={`Rooms (${aggregate.room_count})`} value={fmt(aggregate.subtotal)} />
          {aggregate.mobilization > 0 && (
            <StatRow label="Mobilization" value={fmt(aggregate.mobilization)} />
          )}
          <View style={styles.divider} />
          <StatRow label="Grand Total" value={fmt(aggregate.grand_total)} highlight />
        </Animated.View>

        {/* Rooms list */}
        <View style={styles.section}>
          <SectionLabel style={styles.sectionLabel}>Rooms</SectionLabel>

          {rooms.length === 0 ? (
            <View style={styles.emptyRooms}>
              <Text style={styles.emptyText}>No rooms added yet.</Text>
            </View>
          ) : (
            rooms.map((room, i) => {
              const hasEstimate = recentEstimates.some((e) => e.id === room.estimate_id);
              return (
                <RoomCard
                  key={room.id}
                  room={room}
                  index={i}
                  estimateReady={hasEstimate}
                  onPress={() => handleRoomPress(room)}
                />
              );
            })
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  content: { paddingBottom: 48 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16 },

  // Client
  clientCard: {
    marginHorizontal: 20, marginTop: 4, marginBottom: 4,
    backgroundColor: Colors.surface,
    borderRadius: 12, borderWidth: 1, borderColor: Colors.border,
    padding: 14, gap: 4,
  },
  clientName: { fontSize: 15, fontWeight: '600', color: Colors.text },
  clientAddress: { fontSize: 13, color: Colors.textMuted },

  // Aggregate
  aggregateCard: {
    marginHorizontal: 20, marginTop: 8,
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    padding: 18, gap: 8,
  },
  grandTotal: { fontSize: 40, fontWeight: '800', color: Colors.text, letterSpacing: -1 },
  divider: { height: 1, backgroundColor: Colors.border, marginVertical: 4 },
  statRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statLabel: { fontSize: 14, color: Colors.textMuted },
  statValue: { fontSize: 15, fontWeight: '600', color: Colors.text },
  statValueHL: { fontSize: 17, fontWeight: '800', color: Colors.primary },

  // Section
  section: { paddingHorizontal: 20, marginTop: 24 },
  sectionLabel: { marginBottom: 12 },

  // Room card
  roomCard: {
    backgroundColor: Colors.surface,
    borderRadius: 14, borderWidth: 1, borderColor: Colors.border,
    padding: 16, flexDirection: 'row', alignItems: 'center',
    marginBottom: 10,
  },
  roomLeft: { flex: 1, gap: 4 },
  roomLabel: { fontSize: 15, fontWeight: '700', color: Colors.text },
  roomDate: { fontSize: 12, color: Colors.textSubtle },
  roomRight: { alignItems: 'flex-end', gap: 4 },
  roomTotal: { fontSize: 17, fontWeight: '700', color: Colors.primary },
  roomChevron: { fontSize: 20, color: Colors.textSubtle, fontWeight: '300' },
  roomNoData: { fontSize: 11, color: Colors.textSubtle },

  emptyRooms: { paddingVertical: 24, alignItems: 'center' },
  emptyText: { fontSize: 14, color: Colors.textSubtle },

  // Error
  errorText: { fontSize: 15, color: Colors.textMuted, textAlign: 'center' },
  retryBtn: { paddingHorizontal: 20, paddingVertical: 10 },
  retryText: { fontSize: 15, fontWeight: '600', color: Colors.primary },
});
