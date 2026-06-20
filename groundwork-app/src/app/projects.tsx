import { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, EmptyState } from '@/components';
import { groundworkApi, type Project } from '@/services/api';

function fmtDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return `${diff} days ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function fmtTotal(n: number | null) {
  if (!n) return '—';
  return '$' + Math.round(n).toLocaleString();
}

function statusColor(status: string) {
  if (status === 'active') return Colors.success;
  if (status === 'won') return Colors.primary;
  return Colors.textSubtle;
}

function ProjectCard({ project, index, onPress }: { project: Project; index: number; onPress: () => void }) {
  return (
    <Animated.View entering={FadeInDown.delay(index * 60).duration(350).springify()}>
      <Pressable
        style={({ pressed }) => [styles.card, pressed && { opacity: 0.75 }]}
        onPress={onPress}
      >
        <View style={styles.cardLeft}>
          <View style={styles.cardTitleRow}>
            <Text style={styles.cardName} numberOfLines={1}>{project.name}</Text>
            <View style={[styles.statusDot, { backgroundColor: statusColor(project.status) }]} />
          </View>
          {!!project.client_name && (
            <Text style={styles.cardClient} numberOfLines={1}>👤 {project.client_name}</Text>
          )}
          {!!project.client_address && (
            <Text style={styles.cardAddress} numberOfLines={1}>📍 {project.client_address}</Text>
          )}
          <Text style={styles.cardDate}>{fmtDate(project.created_at)}</Text>
        </View>
        <View style={styles.cardRight}>
          <Text style={styles.cardTotal}>{fmtTotal(project.total_estimate)}</Text>
          <Text style={styles.cardChevron}>›</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

function SkeletonCard() {
  return (
    <View style={[styles.card, { opacity: 0.45 }]}>
      <View style={styles.cardLeft}>
        <View style={[styles.skeletonLine, { width: '60%', height: 14 }]} />
        <View style={[styles.skeletonLine, { width: '40%', height: 11, marginTop: 6 }]} />
        <View style={[styles.skeletonLine, { width: '25%', height: 10, marginTop: 5 }]} />
      </View>
      <View style={{ alignItems: 'flex-end', gap: 6 }}>
        <View style={[styles.skeletonLine, { width: 64, height: 16 }]} />
      </View>
    </View>
  );
}

export default function ProjectsScreen() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const data = await groundworkApi.getProjects();
      setProjects(data);
    } catch {
      setError('Could not load projects.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchProjects(); }, []);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => fetchProjects(true)}
            tintColor={Colors.primary}
          />
        }
      >
        <ScreenHeader title="Projects" onBack={() => router.back()} />

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <SectionLabel style={{ marginBottom: 0 }}>All Projects</SectionLabel>
            {projects.length > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{projects.length}</Text>
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
              <Pressable onPress={() => fetchProjects()} hitSlop={8}>
                <Text style={styles.retryText}>Retry</Text>
              </Pressable>
            </View>
          )}

          {!loading && !error && projects.length === 0 && (
            <EmptyState
              icon="📁"
              title="No projects yet"
              body="Link an estimate to a project from the result screen to get started."
            />
          )}

          {!loading && !error && projects.map((p, i) => (
            <ProjectCard
              key={p.id}
              project={p}
              index={i}
              onPress={() => router.push(`/project/${p.id}` as any)}
            />
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  content: { paddingBottom: 48 },

  section: { paddingHorizontal: 20, paddingTop: 8 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 },
  badge: { backgroundColor: Colors.primary, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  badgeText: { fontSize: 11, fontWeight: '700', color: Colors.white },

  card: {
    backgroundColor: Colors.surface,
    borderRadius: 14, borderWidth: 1, borderColor: Colors.border,
    padding: 16, flexDirection: 'row', alignItems: 'center',
    marginBottom: 10, gap: 12,
  },
  cardLeft: { flex: 1, gap: 4 },
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardName: { fontSize: 15, fontWeight: '700', color: Colors.text, flex: 1 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  cardClient: { fontSize: 13, color: Colors.textMuted },
  cardAddress: { fontSize: 12, color: Colors.textSubtle },
  cardDate: { fontSize: 12, color: Colors.textSubtle, marginTop: 2 },
  cardRight: { alignItems: 'flex-end', gap: 6 },
  cardTotal: { fontSize: 17, fontWeight: '700', color: Colors.primary },
  cardChevron: { fontSize: 20, color: Colors.textSubtle, fontWeight: '300' },

  skeletonLine: { backgroundColor: Colors.surfaceRaised, borderRadius: 4 },

  errorRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12 },
  errorText: { fontSize: 14, color: Colors.textMuted, flex: 1 },
  retryText: { fontSize: 14, fontWeight: '600', color: Colors.primary },
});
