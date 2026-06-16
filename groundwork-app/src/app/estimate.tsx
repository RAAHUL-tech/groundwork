import { useState, useMemo } from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeIn, FadeInDown, LinearTransition } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, ConfidenceBar, PrimaryButton } from '@/components';

// ─── Types ────────────────────────────────────────────────────────────────────
type Tier = 'economy' | 'standard' | 'premium';

interface LineItemDef {
  label: string;
  scope: string;
  qty: number;
  unit: string;
  hdRef?: string;
  source: 'vision' | 'voice';
  material: Record<Tier, number>;
  labor: Record<Tier, number>;
}

// ─── Mock data ────────────────────────────────────────────────────────────────
const LINE_ITEMS: LineItemDef[] = [
  {
    label: 'Cabinet replacement',
    scope: 'Semi-custom cabinets, like-for-like swap',
    qty: 18.5, unit: 'lin ft',
    hdRef: '$159 – $210 / lin ft (Hampton Bay, Home Depot)',
    source: 'vision',
    material: { economy: 90,  standard: 180, premium: 380 },
    labor:    { economy: 55,  standard: 65,  premium: 85  },
  },
  {
    label: 'Quartz countertops',
    scope: 'Full slab replacement, standard edge profile',
    qty: 32, unit: 'sq ft',
    hdRef: '$65 – $130 / sq ft (Home Depot installation)',
    source: 'vision',
    material: { economy: 45,  standard: 75,  premium: 130 },
    labor:    { economy: 30,  standard: 35,  premium: 45  },
  },
  {
    label: 'LVP flooring',
    scope: 'Luxury vinyl plank, full room replacement',
    qty: 210, unit: 'sq ft',
    hdRef: '$2.50 – $8 / sq ft (Home Depot)',
    source: 'vision',
    material: { economy: 2.0, standard: 4.5, premium: 8.0 },
    labor:    { economy: 3.5, standard: 4.0, premium: 5.0 },
  },
  {
    label: 'Sink + faucet replacement',
    scope: 'Drop-in sink with mid-range faucet',
    qty: 1, unit: 'each',
    hdRef: '$150 – $1,200 (Home Depot)',
    source: 'vision',
    material: { economy: 200, standard: 450, premium: 1200 },
    labor:    { economy: 175, standard: 220, premium: 280  },
  },
  {
    label: 'Interior painting',
    scope: 'Walls + ceiling, 2 coats',
    qty: 480, unit: 'sq ft',
    source: 'vision',
    material: { economy: 0.60, standard: 0.90, premium: 1.40 },
    labor:    { economy: 1.80, standard: 2.20, premium: 2.80 },
  },
];

const PERMIT_RATE = 0.08;
const CONTINGENCY_RATE = 0.10;
const CONFIDENCE = { score: 0.84, label: 'High', rangePct: 15 };

// ─── Helpers ──────────────────────────────────────────────────────────────────
function calcItem(item: LineItemDef, tier: Tier) {
  const mat = item.material[tier] * item.qty;
  const lab = item.labor[tier] * item.qty;
  return { mat, lab, total: mat + lab };
}

function fmt(n: number) { return '$' + Math.round(n).toLocaleString(); }
function fmtRate(n: number) { return n >= 10 ? '$' + Math.round(n) : '$' + n.toFixed(2); }

const TIER_LABELS: Record<Tier, string> = {
  economy: 'Economy', standard: 'Standard', premium: 'Premium',
};

const TIER_DESCRIPTIONS: Record<Tier, string> = {
  economy:  'Builder-grade materials, competitive labor',
  standard: 'Mid-range materials, skilled trades',
  premium:  'High-end finishes, specialist craftsmen',
};

// ─── Sub-components ───────────────────────────────────────────────────────────
function TierSelector({ tier, onChange }: { tier: Tier; onChange: (t: Tier) => void }) {
  return (
    <View style={styles.tierCard}>
      <SectionLabel>Finish Tier</SectionLabel>
      <View style={styles.tierRow}>
        {(['economy', 'standard', 'premium'] as Tier[]).map((t) => (
          <Pressable
            key={t}
            style={[styles.tierTab, tier === t && styles.tierTabActive]}
            onPress={() => onChange(t)}
          >
            <Text style={[styles.tierTabText, tier === t && styles.tierTabTextActive]}>
              {TIER_LABELS[t]}
            </Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.tierDesc}>{TIER_DESCRIPTIONS[tier]}</Text>
    </View>
  );
}

function LineItemRow({ item, tier }: { item: LineItemDef; tier: Tier; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const { mat, lab, total } = calcItem(item, tier);

  return (
    <Animated.View layout={LinearTransition.springify()}>
      <Pressable
        style={styles.lineItem}
        onPress={() => setExpanded((v) => !v)}
      >
        <View style={styles.lineItemTop}>
          <View style={styles.lineItemLeft}>
            <Text style={styles.lineItemLabel}>{item.label}</Text>
            <Text style={styles.lineItemScope}>{item.scope}</Text>
          </View>
          <View style={styles.lineItemRight}>
            <Text style={styles.lineItemTotal}>{fmt(total)}</Text>
            <Text style={styles.lineItemExpand}>{expanded ? '▲' : '▼'}</Text>
          </View>
        </View>

        {expanded && (
          <Animated.View entering={FadeIn.duration(200)} style={styles.lineItemDetail}>
            <View style={styles.lineItemDetailRow}>
              <Text style={styles.lineItemDetailLabel}>Quantity</Text>
              <Text style={styles.lineItemDetailValue}>
                {item.qty % 1 === 0 ? item.qty : item.qty.toFixed(1)} {item.unit}
              </Text>
            </View>
            <View style={styles.lineItemDetailRow}>
              <Text style={styles.lineItemDetailLabel}>Material</Text>
              <Text style={styles.lineItemDetailValue}>
                {fmtRate(item.material[tier])} / {item.unit} = {fmt(mat)}
              </Text>
            </View>
            <View style={styles.lineItemDetailRow}>
              <Text style={styles.lineItemDetailLabel}>Labor</Text>
              <Text style={styles.lineItemDetailValue}>
                {fmtRate(item.labor[tier])} / {item.unit} = {fmt(lab)}
              </Text>
            </View>
            {item.hdRef && (
              <View style={styles.hdRef}>
                <Text style={styles.hdRefText}>📦 {item.hdRef}</Text>
              </View>
            )}
          </Animated.View>
        )}
      </Pressable>
      <View style={styles.lineItemDivider} />
    </Animated.View>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function EstimateScreen() {
  const [tier, setTier] = useState<Tier>('standard');

  const summary = useMemo(() => {
    const items = LINE_ITEMS.map((item) => calcItem(item, tier));
    const materials = items.reduce((s, i) => s + i.mat, 0);
    const labor     = items.reduce((s, i) => s + i.lab, 0);
    const subtotal  = materials + labor;
    const permits   = subtotal * PERMIT_RATE;
    const contingency = subtotal * CONTINGENCY_RATE;
    const total     = subtotal + permits + contingency;
    const low       = total * (1 - CONFIDENCE.rangePct / 100);
    const high      = total * (1 + CONFIDENCE.rangePct / 100);
    return { materials, labor, permits, contingency, total, low, high };
  }, [tier]);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.View entering={FadeIn.duration(300)}>
          <ScreenHeader title="Estimate" onBack={() => router.back()} />
        </Animated.View>

        {/* Total hero */}
        <Animated.View entering={FadeInDown.delay(80).duration(400).springify()} style={styles.heroCard}>
          <SectionLabel>Total Estimate</SectionLabel>
          <Text style={styles.heroTotal}>{fmt(summary.total)}</Text>
          <Text style={styles.heroRange}>
            Range: {fmt(summary.low)} – {fmt(summary.high)}
          </Text>

          <View style={styles.confRow}>
            <ConfidenceBar confidence={CONFIDENCE.score} color={Colors.success} />
            <View style={styles.confBadge}>
              <Text style={styles.confBadgeText}>{Math.round(CONFIDENCE.score * 100)}% conf.</Text>
            </View>
          </View>

          <View style={styles.heroMeta}>
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>{fmt(summary.materials)}</Text>
              <Text style={styles.heroMetaLabel}>Materials</Text>
            </View>
            <View style={styles.heroMetaDivider} />
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>{fmt(summary.labor)}</Text>
              <Text style={styles.heroMetaLabel}>Labor</Text>
            </View>
            <View style={styles.heroMetaDivider} />
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>~4 wks</Text>
              <Text style={styles.heroMetaLabel}>Timeline</Text>
            </View>
          </View>
        </Animated.View>

        {/* Tier selector */}
        <Animated.View entering={FadeInDown.delay(160).duration(400).springify()}>
          <TierSelector tier={tier} onChange={setTier} />
        </Animated.View>

        {/* Line items */}
        <Animated.View entering={FadeInDown.delay(220).duration(400)}>
          <SectionLabel style={styles.sectionPad}>Estimate Breakdown</SectionLabel>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(260).duration(400)} style={styles.lineItemsCard}>
          {LINE_ITEMS.map((item, i) => (
            <LineItemRow key={item.label} item={item} tier={tier} index={i} />
          ))}
        </Animated.View>

        {/* Summary table */}
        <Animated.View entering={FadeInDown.delay(320).duration(400)} style={styles.summaryCard}>
          <SectionLabel>Cost Summary</SectionLabel>
          <View style={styles.summaryRows}>
            {[
              { label: 'Materials',          value: summary.materials   },
              { label: 'Labor',              value: summary.labor       },
              { label: 'Permits (8%)',        value: summary.permits     },
              { label: 'Contingency (10%)',   value: summary.contingency },
            ].map(({ label, value }) => (
              <View key={label} style={styles.summaryRow}>
                <Text style={styles.summaryRowLabel}>{label}</Text>
                <Text style={styles.summaryRowValue}>{fmt(value)}</Text>
              </View>
            ))}
            <View style={styles.summaryDivider} />
            <View style={styles.summaryRow}>
              <Text style={styles.summaryTotalLabel}>TOTAL</Text>
              <Text style={styles.summaryTotalValue}>{fmt(summary.total)}</Text>
            </View>
            <View style={[styles.summaryRow, { marginTop: 2 }]}>
              <Text style={styles.summaryRangeLabel}>Low estimate</Text>
              <Text style={styles.summaryRangeValue}>{fmt(summary.low)}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryRangeLabel}>High estimate</Text>
              <Text style={styles.summaryRangeValue}>{fmt(summary.high)}</Text>
            </View>
          </View>
        </Animated.View>

        {/* Regional note */}
        <Animated.View entering={FadeInDown.delay(380).duration(400)} style={styles.regionNote}>
          <Text style={styles.regionNoteText}>
            💡 Prices reflect national averages. Regional multiplier applied at proposal stage based on ZIP code.
          </Text>
        </Animated.View>
      </ScrollView>

      {/* Sticky CTA */}
      <Animated.View entering={FadeInDown.delay(500).duration(400)} style={styles.ctaWrap}>
        <PrimaryButton
          label="Generate Proposal"
          onPress={() => router.push('/proposal' as any)}
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

  sectionPad: { paddingHorizontal: 2 },

  // Hero
  heroCard: {
    backgroundColor: Colors.surface,
    borderRadius: 20, borderWidth: 1, borderColor: Colors.border,
    padding: 20, gap: 10,
  },
  heroTotal: { fontSize: 44, fontWeight: '800', color: Colors.text, letterSpacing: -1 },
  heroRange: { fontSize: 14, color: Colors.textMuted },
  confRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  confBadge: {
    backgroundColor: Colors.successBg, borderRadius: 8,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  confBadgeText: { fontSize: 12, fontWeight: '700', color: Colors.success },
  heroMeta: {
    flexDirection: 'row', borderTopWidth: 1, borderTopColor: Colors.border,
    paddingTop: 12, marginTop: 2,
  },
  heroMetaItem: { flex: 1, alignItems: 'center', gap: 3 },
  heroMetaValue: { fontSize: 16, fontWeight: '700', color: Colors.text },
  heroMetaLabel: { fontSize: 11, color: Colors.textSubtle, fontWeight: '500' },
  heroMetaDivider: { width: 1, backgroundColor: Colors.border, marginVertical: 2 },

  // Tier
  tierCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    padding: 16, gap: 10,
  },
  tierRow: { flexDirection: 'row', gap: 8 },
  tierTab: {
    flex: 1, paddingVertical: 10, borderRadius: 10,
    backgroundColor: Colors.surfaceRaised,
    alignItems: 'center',
    borderWidth: 1, borderColor: 'transparent',
  },
  tierTabActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
    shadowColor: Colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  tierTabText: { fontSize: 13, fontWeight: '700', color: Colors.textMuted },
  tierTabTextActive: { color: Colors.white },
  tierDesc: { fontSize: 13, color: Colors.textSubtle, textAlign: 'center' },

  // Line items
  lineItemsCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    overflow: 'hidden',
  },
  lineItem: { paddingHorizontal: 16, paddingVertical: 14 },
  lineItemTop: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  lineItemLeft: { flex: 1, gap: 2 },
  lineItemLabel: { fontSize: 15, fontWeight: '700', color: Colors.text },
  lineItemScope: { fontSize: 12, color: Colors.textMuted },
  lineItemRight: { alignItems: 'flex-end', gap: 4 },
  lineItemTotal: { fontSize: 17, fontWeight: '700', color: Colors.primary },
  lineItemExpand: { fontSize: 10, color: Colors.textSubtle },
  lineItemDetail: {
    marginTop: 12, gap: 6,
    backgroundColor: Colors.surfaceRaised,
    borderRadius: 10, padding: 12,
  },
  lineItemDetailRow: { flexDirection: 'row', justifyContent: 'space-between' },
  lineItemDetailLabel: { fontSize: 13, color: Colors.textMuted },
  lineItemDetailValue: { fontSize: 13, color: Colors.text, fontWeight: '500' },
  hdRef: { marginTop: 4, backgroundColor: Colors.background, borderRadius: 8, padding: 8 },
  hdRefText: { fontSize: 11, color: Colors.textSubtle },
  lineItemDivider: { height: 1, backgroundColor: Colors.border, marginLeft: 16 },

  // Summary
  summaryCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    padding: 18, gap: 0,
  },
  summaryRows: { gap: 10 },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  summaryRowLabel: { fontSize: 15, color: Colors.textMuted },
  summaryRowValue: { fontSize: 15, fontWeight: '600', color: Colors.text },
  summaryDivider: { height: 1, backgroundColor: Colors.border, marginVertical: 4 },
  summaryTotalLabel: { fontSize: 16, fontWeight: '800', color: Colors.text, letterSpacing: 0.5 },
  summaryTotalValue: { fontSize: 22, fontWeight: '800', color: Colors.primary },
  summaryRangeLabel: { fontSize: 13, color: Colors.textSubtle },
  summaryRangeValue: { fontSize: 13, color: Colors.textSubtle, fontWeight: '500' },

  // Region note
  regionNote: {
    backgroundColor: Colors.surface,
    borderRadius: 12, borderWidth: 1, borderColor: Colors.border,
    padding: 14,
  },
  regionNoteText: { fontSize: 13, color: Colors.textSubtle, lineHeight: 19 },

  // CTA
  ctaWrap: {
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },
});
