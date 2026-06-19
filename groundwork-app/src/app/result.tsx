import { ScrollView, StyleSheet, Text, View, Pressable, Modal, FlatList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import Animated, { FadeIn, FadeInDown, FadeInLeft } from 'react-native-reanimated';
import { useState, useEffect, useCallback } from 'react';
import { Colors } from '@/constants/colors';
import {
  SectionLabel,
  Badge,
  Card,
  ConfidenceBar,
  PrimaryButton,
  confidenceColor,
  confidenceLabel,
} from '@/components';
import { getEstimateResult, getEstimateJobId, setProjectClient } from '@/services/estimateStore';
import { groundworkApi } from '@/services/api';
import type { VisionDetectedFeature, Project, ProjectAggregate } from '@/services/api';

// Map API label strings to display icons
const ITEM_ICONS: Record<string, string> = {
  cabinets: '🗄️', countertop: '🪨', countertops: '🪨',
  sink: '🚰', dishwasher: '🍽️', refrigerator: '❄️', range: '🔥',
  flooring: '⬜', windows: '🪟', window: '🪟',
  lighting: '💡', toilet: '🚽', tub: '🛁', shower: '🚿',
  vanity: '🪞', door: '🚪', paint: '🎨', backsplash: '🧱',
  appliance: '⚡', microwave: '📦', hood: '🌬️',
};

function iconForLabel(label: string): string {
  const key = label.toLowerCase();
  for (const [k, icon] of Object.entries(ITEM_ICONS)) {
    if (key.includes(k)) return icon;
  }
  return '🔧';
}

type Condition = 'poor' | 'fair' | 'good' | 'excellent';

function conditionColor(c: string): string {
  return (
    { poor: Colors.error, fair: Colors.warning, good: Colors.success, excellent: Colors.primary }[c as Condition]
    ?? Colors.textMuted
  );
}

function conditionLabel(c: string): string {
  return c.charAt(0).toUpperCase() + c.slice(1);
}

function fmtQty(qty: number | null, unit: string | null): string {
  if (qty == null) return '';
  const q = qty % 1 === 0 ? qty.toString() : qty.toFixed(1);
  return unit ? `${q} ${unit.replace('_', ' ')}` : q;
}

// Normalise API result to UI shape
function normaliseResult(raw: ReturnType<typeof getEstimateResult>) {
  if (!raw) return null;
  return {
    room_type: raw.room_type.charAt(0).toUpperCase() + raw.room_type.slice(1).replace(/_/g, ' '),
    room_confidence: raw.room_confidence,
    condition: raw.condition ?? 'fair',
    condition_notes: raw.condition_notes ?? '',
    scope_observations: raw.scope_narrative ?? '',
    // What Claude Vision actually SAW — used here in the result UI
    vision_features: (raw.vision_detected_features ?? []).map((f) => ({
      ...f,
      icon: iconForLabel(f.item),
      displayLabel: f.item.charAt(0).toUpperCase() + f.item.slice(1).replace(/_/g, ' '),
    })),
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────
function RoomCard({ roomType, confidence }: { roomType: string; confidence: number }) {
  const color = confidenceColor(confidence);
  const pct = Math.round(confidence * 100);

  return (
    <Animated.View entering={FadeInDown.delay(100).duration(400).springify()}>
      <Card style={styles.roomCard}>
        <View style={styles.roomCardTop}>
          <View>
            <SectionLabel>Room Type</SectionLabel>
            <Text style={styles.roomType}>{roomType}</Text>
          </View>
          <Badge label={`${pct}% ${confidenceLabel(confidence)}`} color={color} />
        </View>
        <ConfidenceBar confidence={confidence} />
      </Card>
    </Animated.View>
  );
}

function ConditionRow({ condition, notes }: { condition: string; notes: string }) {
  const color = conditionColor(condition);
  return (
    <Animated.View entering={FadeInDown.delay(200).duration(400)}>
      <Card style={styles.conditionCard}>
        <View style={styles.conditionRow}>
          <SectionLabel>Condition</SectionLabel>
          <Badge label={conditionLabel(condition)} color={color} />
        </View>
        {!!notes && <Text style={styles.conditionNotes}>{notes}</Text>}
      </Card>
    </Animated.View>
  );
}

function FeatureRow({
  icon, displayLabel, condition, estimated_qty, unit, notes, index,
}: VisionDetectedFeature & { icon: string; displayLabel: string; index: number }) {
  const condColor = conditionColor(condition);
  const qtyStr = fmtQty(estimated_qty, unit);

  return (
    <Animated.View
      entering={FadeInLeft.delay(300 + index * 55).duration(350).springify()}
      style={styles.itemRow}
    >
      <View style={styles.itemIconWrap}>
        <Text style={styles.itemIcon}>{icon}</Text>
      </View>
      <View style={styles.itemMeta}>
        <Text style={styles.itemLabel}>{displayLabel}</Text>
        {!!qtyStr && <Text style={styles.itemQty}>{qtyStr}</Text>}
        {!!notes && <Text style={styles.itemNotes}>{notes}</Text>}
      </View>
      <View style={[styles.condBadge, { backgroundColor: condColor + '22' }]}>
        <Text style={[styles.condBadgeText, { color: condColor }]}>
          {conditionLabel(condition)}
        </Text>
      </View>
    </Animated.View>
  );
}

// ─── Project picker ───────────────────────────────────────────────────────────
function ProjectPickerModal({
  visible,
  projects,
  onSelect,
  onClose,
}: {
  visible: boolean;
  projects: Project[];
  onSelect: (p: Project) => void;
  onClose: () => void;
}) {
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <SafeAreaView style={pickerStyles.container} edges={['top', 'bottom']}>
        <View style={pickerStyles.header}>
          <Text style={pickerStyles.title}>Select a Project</Text>
          <Pressable onPress={onClose} hitSlop={12}>
            <Text style={pickerStyles.closeBtn}>✕</Text>
          </Pressable>
        </View>
        {projects.length === 0 ? (
          <View style={pickerStyles.empty}>
            <Text style={pickerStyles.emptyText}>No projects found.</Text>
            <Text style={pickerStyles.emptyHint}>Create a project in the Projects tab first.</Text>
          </View>
        ) : (
          <FlatList
            data={projects}
            keyExtractor={(p) => p.id}
            contentContainerStyle={{ padding: 16, gap: 10 }}
            renderItem={({ item: p }) => (
              <Pressable style={pickerStyles.projectRow} onPress={() => onSelect(p)}>
                <View style={{ flex: 1 }}>
                  <Text style={pickerStyles.projectName}>{p.name}</Text>
                  {!!p.client_name && (
                    <Text style={pickerStyles.projectClient}>{p.client_name}</Text>
                  )}
                </View>
                {p.total_estimate != null && (
                  <Text style={pickerStyles.projectTotal}>
                    ${Math.round(p.total_estimate).toLocaleString()}
                  </Text>
                )}
                <Text style={pickerStyles.chevron}>›</Text>
              </Pressable>
            )}
          />
        )}
      </SafeAreaView>
    </Modal>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function ResultScreen() {
  const { captureMode } = useLocalSearchParams<{ captureMode: string }>();
  const result = normaliseResult(getEstimateResult());

  // Project-picker state
  const [projects, setProjects]             = useState<Project[]>([]);
  const [pickerVisible, setPickerVisible]   = useState(false);
  const [linking, setLinking]               = useState(false);
  const [linked, setLinked]                 = useState<ProjectAggregate | null>(null);
  const [linkError, setLinkError]           = useState<string | null>(null);

  useEffect(() => {
    groundworkApi.getProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  const handleSelectProject = useCallback(async (project: Project) => {
    setPickerVisible(false);
    setLinking(true);
    setLinkError(null);
    const jobId = getEstimateJobId();
    if (!jobId) {
      setLinkError('No estimate job found. Please run an estimate first.');
      setLinking(false);
      return;
    }
    try {
      const agg = await groundworkApi.addRoomToProject({
        project_id: project.id,
        estimate_job_id: jobId,
      });
      setLinked(agg);
      setProjectClient({
        name:    agg.client_name    ?? project.client_name    ?? '',
        address: agg.client_address ?? project.client_address ?? '',
      });
    } catch (e: any) {
      setLinkError(e?.message ?? 'Failed to link to project.');
    } finally {
      setLinking(false);
    }
  }, []);

  // If no result yet, show a minimal placeholder
  if (!result) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ color: Colors.textMuted, fontSize: 16 }}>No analysis available.</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.View entering={FadeIn.duration(350)} style={styles.header}>
          <Pressable style={styles.backBtn} onPress={() => router.back()} hitSlop={12}>
            <Text style={styles.backBtnText}>←</Text>
          </Pressable>
          <View style={styles.successBadge}>
            <Text style={styles.successBadgeText}>✓  Analysis Complete</Text>
          </View>
          <View style={{ width: 40 }} />
        </Animated.View>

        {/* Room classification */}
        <RoomCard roomType={result.room_type} confidence={result.room_confidence} />

        {/* Condition */}
        <ConditionRow condition={result.condition} notes={result.condition_notes} />

        {/* Scope observations */}
        {!!result.scope_observations && (
          <Animated.View entering={FadeInDown.delay(250).duration(400)}>
            <Card style={styles.scopeCard}>
              <SectionLabel>Scope Observations</SectionLabel>
              <Text style={styles.scopeText}>{result.scope_observations}</Text>
            </Card>
          </Animated.View>
        )}

        {/* Detected objects — from Claude Vision 1st call only */}
        {result.vision_features.length > 0 && (
          <>
            <Animated.View
              entering={FadeInDown.delay(280).duration(400)}
              style={styles.sectionHeader}
            >
              <SectionLabel>Detected Objects</SectionLabel>
              <View style={styles.countBadge}>
                <Text style={styles.countBadgeText}>{result.vision_features.length}</Text>
              </View>
            </Animated.View>

            <View style={styles.itemsCard}>
              {result.vision_features.map((feat, i) => (
                <View key={feat.item}>
                  <FeatureRow {...feat} index={i} />
                  {i < result.vision_features.length - 1 && (
                    <View style={styles.itemDivider} />
                  )}
                </View>
              ))}
            </View>
          </>
        )}
        {/* Add to Project */}
        <Animated.View entering={FadeInDown.delay(500).duration(400)}>
          <Card style={styles.projectCard}>
            <SectionLabel>Add to Project</SectionLabel>

            {linked ? (
              /* ── Success state ── */
              <View style={styles.linkedWrap}>
                <View style={styles.linkedBadge}>
                  <Text style={styles.linkedBadgeText}>✓  Added to {linked.name}</Text>
                </View>
                <View style={styles.aggregateRow}>
                  <View style={styles.aggregateStat}>
                    <Text style={styles.aggregateStatLabel}>Rooms</Text>
                    <Text style={styles.aggregateStatValue}>{linked.aggregate.room_count}</Text>
                  </View>
                  <View style={styles.aggregateDivider} />
                  <View style={styles.aggregateStat}>
                    <Text style={styles.aggregateStatLabel}>Project Total</Text>
                    <Text style={[styles.aggregateStatValue, { color: Colors.primary }]}>
                      ${linked.aggregate.grand_total.toLocaleString()}
                    </Text>
                  </View>
                  {linked.aggregate.mobilization > 0 && (
                    <>
                      <View style={styles.aggregateDivider} />
                      <View style={styles.aggregateStat}>
                        <Text style={styles.aggregateStatLabel}>Mobilization</Text>
                        <Text style={styles.aggregateStatValue}>
                          +${linked.aggregate.mobilization.toLocaleString()}
                        </Text>
                      </View>
                    </>
                  )}
                </View>
              </View>
            ) : linking ? (
              /* ── Loading ── */
              <View style={styles.linkingWrap}>
                <ActivityIndicator size="small" color={Colors.primary} />
                <Text style={styles.linkingText}>Linking to project…</Text>
              </View>
            ) : (
              /* ── Default state ── */
              <View style={styles.projectPickerWrap}>
                {!!linkError && (
                  <Text style={styles.linkError}>{linkError}</Text>
                )}
                <Text style={styles.projectHint}>
                  Associate this scan with an existing project to track multi-room totals.
                </Text>
                <Pressable
                  style={styles.selectProjectBtn}
                  onPress={() => setPickerVisible(true)}
                >
                  <Text style={styles.selectProjectBtnText}>Select Project</Text>
                </Pressable>
              </View>
            )}
          </Card>
        </Animated.View>
      </ScrollView>

      {/* Project picker modal */}
      <ProjectPickerModal
        visible={pickerVisible}
        projects={projects}
        onSelect={handleSelectProject}
        onClose={() => setPickerVisible(false)}
      />

      {/* Sticky CTA */}
      <Animated.View entering={FadeInDown.delay(600).duration(400)} style={styles.ctaWrap}>
        <PrimaryButton
          label="Generate Estimate"
          onPress={() => router.push({ pathname: '/estimate' as any, params: { captureMode } })}
        />
      </Animated.View>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 24, gap: 12 },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 12,
    paddingBottom: 4,
  },
  backBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: Colors.surface,
    alignItems: 'center', justifyContent: 'center',
  },
  backBtnText: { fontSize: 20, color: Colors.text, fontWeight: '600' },
  successBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.successBg,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  successBadgeText: {
    fontSize: 13, fontWeight: '700', color: Colors.success, letterSpacing: 0.3,
  },

  // Room card
  roomCard: { gap: 14 },
  roomCardTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  roomType: { fontSize: 32, fontWeight: '800', color: Colors.text, letterSpacing: -0.5 },

  // Condition card
  conditionCard: { gap: 10 },
  conditionRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
  },
  conditionNotes: { fontSize: 14, color: Colors.textMuted, lineHeight: 21 },

  // Scope
  scopeCard: { gap: 8 },
  scopeText: { fontSize: 14, color: Colors.textMuted, lineHeight: 22 },

  // Section header
  sectionHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 2, marginTop: 4,
  },
  countBadge: {
    backgroundColor: Colors.primary, borderRadius: 10,
    paddingHorizontal: 8, paddingVertical: 2,
  },
  countBadgeText: { fontSize: 11, fontWeight: '700', color: Colors.white },

  // Items
  itemsCard: {
    backgroundColor: Colors.surface, borderRadius: 16,
    borderWidth: 1, borderColor: Colors.border, overflow: 'hidden',
  },
  itemRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 13, gap: 12,
  },
  itemIconWrap: {
    width: 38, height: 38, borderRadius: 10,
    backgroundColor: Colors.surfaceRaised,
    alignItems: 'center', justifyContent: 'center',
  },
  itemIcon: { fontSize: 18 },
  itemMeta: { flex: 1, gap: 2 },
  itemLabel: { fontSize: 15, fontWeight: '600', color: Colors.text },
  itemQty: { fontSize: 13, color: Colors.textMuted },
  itemNotes: { fontSize: 12, color: Colors.textMuted, fontStyle: 'italic', marginTop: 2 },
  condBadge: { borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4 },
  condBadgeText: { fontSize: 12, fontWeight: '700' },
  itemDivider: { height: 1, backgroundColor: Colors.border, marginLeft: 66 },

  // Sticky CTA
  ctaWrap: {
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },

  // Add to Project card
  projectCard: { gap: 12 },
  projectPickerWrap: { gap: 10 },
  projectHint: { fontSize: 13, color: Colors.textMuted, lineHeight: 20 },
  selectProjectBtn: {
    backgroundColor: Colors.primary,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  selectProjectBtnText: { fontSize: 15, fontWeight: '700', color: Colors.white },
  linkingWrap: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 4 },
  linkingText: { fontSize: 14, color: Colors.textMuted },
  linkError: { fontSize: 13, color: Colors.error, lineHeight: 19 },

  // Success aggregate
  linkedWrap: { gap: 12 },
  linkedBadge: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.successBg,
    borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7,
    alignSelf: 'flex-start',
  },
  linkedBadgeText: { fontSize: 13, fontWeight: '700', color: Colors.success },
  aggregateRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surfaceRaised,
    borderRadius: 12, padding: 14, gap: 0,
  },
  aggregateStat: { flex: 1, alignItems: 'center', gap: 4 },
  aggregateStatLabel: { fontSize: 11, color: Colors.textMuted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.4 },
  aggregateStatValue: { fontSize: 18, fontWeight: '800', color: Colors.text },
  aggregateDivider: { width: 1, height: 32, backgroundColor: Colors.border },
});

// ─── Picker modal styles ──────────────────────────────────────────────────────
const pickerStyles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 16,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  title: { fontSize: 18, fontWeight: '700', color: Colors.text },
  closeBtn: { fontSize: 18, color: Colors.textMuted, fontWeight: '600' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 40 },
  emptyText: { fontSize: 16, fontWeight: '600', color: Colors.text },
  emptyHint: { fontSize: 14, color: Colors.textMuted, textAlign: 'center' },
  projectRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: 14, padding: 16,
    borderWidth: 1, borderColor: Colors.border,
    gap: 8,
  },
  projectName: { fontSize: 16, fontWeight: '700', color: Colors.text },
  projectClient: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },
  projectTotal: { fontSize: 15, fontWeight: '700', color: Colors.primary },
  chevron: { fontSize: 22, color: Colors.textMuted },
});
