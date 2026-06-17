import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import Animated, { FadeIn, FadeInDown, FadeInLeft } from 'react-native-reanimated';
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
import { getEstimateResult } from '@/services/estimateStore';

// ─── Mock data ────────────────────────────────────────────────────────────────
const MOCK_RESULT = {
  room_type: 'Kitchen',
  room_confidence: 0.94,
  condition: 'fair' as const,
  condition_notes:
    'Dated cabinets with original hardware, laminate countertops showing wear, tile flooring in fair condition.',
  scope_observations:
    'Mid-1990s kitchen likely needing full renovation. Cabinet replacement, countertop upgrade, and flooring update are the primary scope items.',
  detected_items: [
    { label: 'Cabinets',          icon: '🗄️',  confidence: 0.91, quantity: 18.5, unit: 'linear ft' },
    { label: 'Countertops',       icon: '🪨',  confidence: 0.88, quantity: 32,   unit: 'sq ft'    },
    { label: 'Sink',              icon: '🚰',  confidence: 0.95, quantity: 1,    unit: 'each'     },
    { label: 'Dishwasher',        icon: '🍽️', confidence: 0.82, quantity: 1,    unit: 'each'     },
    { label: 'Refrigerator',      icon: '❄️',  confidence: 0.97, quantity: 1,    unit: 'each'     },
    { label: 'Flooring',          icon: '⬜',  confidence: 0.93, quantity: 210,  unit: 'sq ft'    },
    { label: 'Windows',           icon: '🪟',  confidence: 0.79, quantity: 2,    unit: 'each'     },
    { label: 'Lighting Fixtures', icon: '💡',  confidence: 0.86, quantity: 3,    unit: 'each'     },
  ],
};

// Map API label strings to display icons
const ITEM_ICONS: Record<string, string> = {
  cabinets: '🗄️', countertop: '🪨', countertops: '🪨',
  sink: '🚰', dishwasher: '🍽️', refrigerator: '❄️', range: '🔥',
  flooring: '⬜', windows: '🪟', window: '🪟',
  lighting: '💡', toilet: '🚽', tub: '🛁', shower: '🚿',
  vanity: '🪞', door: '🚪', paint: '🎨',
};

function iconForLabel(label: string): string {
  const key = label.toLowerCase();
  for (const [k, icon] of Object.entries(ITEM_ICONS)) {
    if (key.includes(k)) return icon;
  }
  return '🔧';
}

// Normalise API result to the shape the UI expects
function normaliseResult(raw: ReturnType<typeof getEstimateResult>) {
  if (!raw) return MOCK_RESULT;
  return {
    room_type: raw.room_type.charAt(0).toUpperCase() + raw.room_type.slice(1).replace('_', ' '),
    room_confidence: raw.room_confidence,
    condition: (raw.condition ?? 'fair') as 'poor' | 'fair' | 'good' | 'excellent',
    condition_notes: raw.condition_notes ?? '',
    scope_observations: raw.scope_narrative ?? '',
    detected_items: (raw.detected_items ?? []).map((item) => ({
      label: item.label.charAt(0).toUpperCase() + item.label.slice(1).replace(/_/g, ' '),
      icon: iconForLabel(item.label),
      confidence: item.confidence,
      quantity: item.quantity ?? 0,
      unit: item.unit ?? '',
    })),
  };
}

type Condition = 'poor' | 'fair' | 'good' | 'excellent';

function conditionColor(c: Condition) {
  return { poor: Colors.error, fair: Colors.warning, good: Colors.success, excellent: Colors.primary }[c];
}

function fmtQty(qty: number) {
  return qty % 1 === 0 ? qty.toString() : qty.toFixed(1);
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

function ConditionRow({ condition, notes }: { condition: Condition; notes: string }) {
  const color = conditionColor(condition);
  return (
    <Animated.View entering={FadeInDown.delay(200).duration(400)}>
      <Card style={styles.conditionCard}>
        <View style={styles.conditionRow}>
          <SectionLabel>Condition</SectionLabel>
          <Badge
            label={condition.charAt(0).toUpperCase() + condition.slice(1)}
            color={color}
          />
        </View>
        <Text style={styles.conditionNotes}>{notes}</Text>
      </Card>
    </Animated.View>
  );
}

function DetectedItem({
  icon, label, confidence, quantity, unit, index,
}: (typeof MOCK_RESULT.detected_items)[0] & { index: number }) {
  const color = confidenceColor(confidence);
  return (
    <Animated.View
      entering={FadeInLeft.delay(300 + index * 60).duration(350).springify()}
      style={styles.itemRow}
    >
      <View style={styles.itemIconWrap}>
        <Text style={styles.itemIcon}>{icon}</Text>
      </View>
      <View style={styles.itemMeta}>
        <Text style={styles.itemLabel}>{label}</Text>
        <Text style={styles.itemQty}>{fmtQty(quantity)} {unit}</Text>
      </View>
      <View style={[styles.itemConfBadge, { backgroundColor: color + '22' }]}>
        <Text style={[styles.itemConfText, { color }]}>{Math.round(confidence * 100)}%</Text>
      </View>
    </Animated.View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function ResultScreen() {
  const { captureMode } = useLocalSearchParams<{ captureMode: string }>();
  const result = normaliseResult(getEstimateResult());

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

        {/* Room classification card */}
        <RoomCard roomType={result.room_type} confidence={result.room_confidence} />

        {/* Condition card */}
        <ConditionRow condition={result.condition} notes={result.condition_notes} />

        {/* Scope observations */}
        <Animated.View entering={FadeInDown.delay(250).duration(400)}>
          <Card style={styles.scopeCard}>
            <SectionLabel>Scope Observations</SectionLabel>
            <Text style={styles.scopeText}>{result.scope_observations}</Text>
          </Card>
        </Animated.View>

        {/* Detected items header */}
        <Animated.View entering={FadeInDown.delay(280).duration(400)} style={styles.sectionHeader}>
          <SectionLabel>Detected Objects</SectionLabel>
          <View style={styles.countBadge}>
            <Text style={styles.countBadgeText}>{result.detected_items.length}</Text>
          </View>
        </Animated.View>

        <View style={styles.itemsCard}>
          {result.detected_items.map((item, i) => (
            <View key={item.label}>
              <DetectedItem {...item} index={i} />
              {i < result.detected_items.length - 1 && <View style={styles.itemDivider} />}
            </View>
          ))}
        </View>
      </ScrollView>

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
  itemConfBadge: { borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4 },
  itemConfText: { fontSize: 13, fontWeight: '700' },
  itemDivider: { height: 1, backgroundColor: Colors.border, marginLeft: 66 },

  // Sticky CTA
  ctaWrap: {
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },
});
