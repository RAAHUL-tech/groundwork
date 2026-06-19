import { useState, useMemo } from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeIn, FadeInDown, LinearTransition } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, ConfidenceBar, PrimaryButton } from '@/components';
import { getEstimateResult } from '@/services/estimateStore';
import type { LineItem, TierEstimate } from '@/services/api';

// ─── Types ────────────────────────────────────────────────────────────────────
type Tier = 'economy' | 'standard' | 'premium';

const TIER_LABELS: Record<Tier, string> = {
  economy: 'Economy', standard: 'Standard', premium: 'Premium',
};
const TIER_DESCRIPTIONS: Record<Tier, string> = {
  economy:  'Builder-grade materials, competitive labor',
  standard: 'Mid-range materials, skilled trades',
  premium:  'High-end finishes, specialist craftsmen',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(n: number) { return '$' + Math.round(n).toLocaleString(); }
function fmtRate(n: number) { return n >= 10 ? '$' + Math.round(n) : '$' + n.toFixed(2); }

// ─── Sub-components ───────────────────────────────────────────────────────────

function TierCompare({
  tiers,
  selected,
  onSelect,
}: {
  tiers: Record<Tier, TierEstimate>;
  selected: Tier;
  onSelect: (t: Tier) => void;
}) {
  return (
    <View style={styles.tierCard}>
      <SectionLabel>Finish Tier</SectionLabel>
      <View style={styles.tierRow}>
        {(['economy', 'standard', 'premium'] as Tier[]).map((t) => {
          const active = t === selected;
          return (
            <Pressable
              key={t}
              style={[styles.tierTab, active && styles.tierTabActive]}
              onPress={() => onSelect(t)}
            >
              <Text style={[styles.tierTabLabel, active && styles.tierTabLabelActive]}>
                {TIER_LABELS[t]}
              </Text>
              <Text style={[styles.tierTabTotal, active && styles.tierTabTotalActive]}>
                {fmt(tiers[t].total)}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.tierDesc}>{TIER_DESCRIPTIONS[selected]}</Text>
    </View>
  );
}

function LineItemRow({ item, index }: { item: LineItem; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const matTotal = item.material_unit_cost * item.qty;
  const labTotal = item.labor_unit_cost * item.qty;

  return (
    <Animated.View layout={LinearTransition.springify()}>
      <Pressable style={styles.lineItem} onPress={() => setExpanded((v) => !v)}>
        <View style={styles.lineItemTop}>
          <View style={styles.lineItemLeft}>
            <Text style={styles.lineItemLabel}>{item.item}</Text>
            {item.scope ? <Text style={styles.lineItemScope}>{item.scope}</Text> : null}
          </View>
          <View style={styles.lineItemRight}>
            <Text style={styles.lineItemTotal}>{fmt(item.total)}</Text>
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
                {fmtRate(item.material_unit_cost)}/{item.unit} = {fmt(matTotal)}
              </Text>
            </View>
            <View style={styles.lineItemDetailRow}>
              <Text style={styles.lineItemDetailLabel}>Labor</Text>
              <Text style={styles.lineItemDetailValue}>
                {fmtRate(item.labor_unit_cost)}/{item.unit} = {fmt(labTotal)}
              </Text>
            </View>
            {item.hd_price_reference && (
              <View style={styles.hdRef}>
                <Text style={styles.hdRefText}>🏠 {item.hd_price_reference}</Text>
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
  const raw = getEstimateResult();
  const [tier, setTier] = useState<Tier>(() => {
    const t = raw?.tier;
    if (t === 'eco' || t === 'economy') return 'economy';
    if (t === 'premium') return 'premium';
    return 'standard';
  });

  // Build tier data — prefer pre-computed tier_estimates from API;
  // fall back to constructing from the primary result when not available.
  const tiers = useMemo<Record<Tier, TierEstimate>>(() => {
    if (raw?.tier_estimates) {
      return raw.tier_estimates;
    }
    // Fallback: all 3 show the same tier (single-tier API response)
    const fallback: TierEstimate = {
      total:              raw?.total_estimate ?? 0,
      range:              raw?.estimate_range ?? { low: 0, high: 0 },
      subtotal_materials: raw?.subtotal_materials ?? 0,
      subtotal_labor:     raw?.subtotal_labor ?? 0,
      permits:            raw?.permits ?? 0,
      contingency:        raw?.contingency ?? 0,
      breakdown:          raw?.estimate_breakdown ?? [],
      timeline_weeks:     raw?.timeline_estimate_weeks ?? 4,
    };
    return { economy: fallback, standard: fallback, premium: fallback };
  }, [raw]);

  const current = tiers[tier];
  const confidence = raw?.confidence ?? { score: 0.75, label: 'Medium', range_pct: 20 };
  const regionMultiplier = raw?.regional_multiplier ?? 1.0;
  const zipCode = raw?.zip_code ?? '—';

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.View entering={FadeIn.duration(300)}>
          <ScreenHeader
            title={raw?.room_type
              ? raw.room_type.charAt(0).toUpperCase() + raw.room_type.slice(1).replace(/_/g, ' ') + ' Estimate'
              : 'Estimate'}
            onBack={() => router.back()}
          />
        </Animated.View>

        {/* Total hero */}
        <Animated.View entering={FadeInDown.delay(80).duration(400).springify()} style={styles.heroCard}>
          <SectionLabel>Total Estimate</SectionLabel>
          <Text style={styles.heroTotal}>{fmt(current.total)}</Text>
          <Text style={styles.heroRange}>
            Range: {fmt(current.range.low)} – {fmt(current.range.high)}
          </Text>

          <View style={styles.confRow}>
            <ConfidenceBar confidence={confidence.score} color={Colors.success} />
            <View style={styles.confBadge}>
              <Text style={styles.confBadgeText}>{Math.round(confidence.score * 100)}% conf.</Text>
            </View>
          </View>

          {/* Materials / Labor / Timeline */}
          <View style={styles.heroMeta}>
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>{fmt(current.subtotal_materials)}</Text>
              <Text style={styles.heroMetaLabel}>Materials</Text>
            </View>
            <View style={styles.heroMetaDivider} />
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>{fmt(current.subtotal_labor)}</Text>
              <Text style={styles.heroMetaLabel}>Labor</Text>
            </View>
            <View style={styles.heroMetaDivider} />
            <View style={styles.heroMetaItem}>
              <Text style={styles.heroMetaValue}>~{current.timeline_weeks} wks</Text>
              <Text style={styles.heroMetaLabel}>Timeline</Text>
            </View>
          </View>
        </Animated.View>

        {/* Tier selector with live totals */}
        <Animated.View entering={FadeInDown.delay(160).duration(400).springify()}>
          <TierCompare tiers={tiers} selected={tier} onSelect={setTier} />
        </Animated.View>

        {/* Line items */}
        <Animated.View entering={FadeInDown.delay(220).duration(400)}>
          <SectionLabel style={styles.sectionPad}>Estimate Breakdown</SectionLabel>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(260).duration(400)} style={styles.lineItemsCard}>
          {current.breakdown.length > 0
            ? current.breakdown.map((item, i) => (
                <LineItemRow key={item.item + i} item={item} index={i} />
              ))
            : (
              <View style={styles.emptyBreakdown}>
                <Text style={styles.emptyBreakdownText}>No line items yet</Text>
              </View>
            )}
        </Animated.View>

        {/* Cost summary */}
        <Animated.View entering={FadeInDown.delay(320).duration(400)} style={styles.summaryCard}>
          <SectionLabel>Cost Summary</SectionLabel>
          <View style={styles.summaryRows}>
            {[
              { label: 'Materials',        value: current.subtotal_materials },
              { label: 'Labor',            value: current.subtotal_labor },
              { label: 'Permits (8%)',     value: current.permits },
              { label: 'Contingency (10%)',value: current.contingency },
            ].map(({ label, value }) => (
              <View key={label} style={styles.summaryRow}>
                <Text style={styles.summaryRowLabel}>{label}</Text>
                <Text style={styles.summaryRowValue}>{fmt(value)}</Text>
              </View>
            ))}
            <View style={styles.summaryDivider} />
            <View style={styles.summaryRow}>
              <Text style={styles.summaryTotalLabel}>TOTAL</Text>
              <Text style={styles.summaryTotalValue}>{fmt(current.total)}</Text>
            </View>
            <View style={[styles.summaryRow, { marginTop: 2 }]}>
              <Text style={styles.summaryRangeLabel}>Low estimate</Text>
              <Text style={styles.summaryRangeValue}>{fmt(current.range.low)}</Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryRangeLabel}>High estimate</Text>
              <Text style={styles.summaryRangeValue}>{fmt(current.range.high)}</Text>
            </View>
          </View>
        </Animated.View>

        {/* Regional / pricing note */}
        <Animated.View entering={FadeInDown.delay(380).duration(400)} style={styles.regionNote}>
          <Text style={styles.regionNoteText}>
            📍 ZIP {zipCode} · {regionMultiplier.toFixed(2)}× regional cost multiplier applied
            {raw?.tier_estimates
              ? '  ·  Live Home Depot pricing where available'
              : '  ·  RSMeans national average pricing'}
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
    flex: 1, paddingVertical: 10, paddingHorizontal: 4,
    borderRadius: 10, backgroundColor: Colors.surfaceRaised,
    alignItems: 'center', gap: 3,
    borderWidth: 1, borderColor: 'transparent',
  },
  tierTabActive: {
    backgroundColor: Colors.primary, borderColor: Colors.primary,
    shadowColor: Colors.primary, shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  tierTabLabel: { fontSize: 11, fontWeight: '700', color: Colors.textMuted },
  tierTabLabelActive: { color: 'rgba(255,255,255,0.85)' },
  tierTabTotal: { fontSize: 13, fontWeight: '800', color: Colors.text },
  tierTabTotalActive: { color: Colors.white },
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
  emptyBreakdown: { padding: 24, alignItems: 'center' },
  emptyBreakdownText: { fontSize: 14, color: Colors.textSubtle },

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
  regionNoteText: { fontSize: 12, color: Colors.textSubtle, lineHeight: 19 },

  // CTA
  ctaWrap: {
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },
});
