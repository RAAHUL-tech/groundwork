import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable, Share, Linking, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeIn, FadeInDown, FadeInUp } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, LogoMark } from '@/components';
import { getEstimateResult, getEstimateJobId, getProjectClient } from '@/services/estimateStore';
import { groundworkApi } from '@/services/api';

// ─── Demo contractor info (Phase 2: comes from user profile) ─────────────────
const CONTRACTOR = {
  name:    'Mike Torres',
  company: 'Torres Construction LLC',
  license: 'CA-GC-889234',
  phone:   '714-555-0192',
  email:   'mike@torresconstruction.com',
};

const FALLBACK_CLIENT = {
  name:    'Homeowner',
  address: '',
  phone:   '',
  email:   '',
};

const PAYMENT_TERMS = '50% deposit due at signing, 50% on completion';
const VALID_DAYS    = 30;

function fmt(n: number) { return '$' + Math.round(n).toLocaleString(); }

function fmtDate(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

// ─── Document preview ─────────────────────────────────────────────────────────
function ProposalDocument({
  estimate,
  propId,
  client,
}: {
  estimate: NonNullable<ReturnType<typeof getEstimateResult>>;
  propId: string;
  client: typeof FALLBACK_CLIENT;
}) {
  const lineItems = estimate.estimate_breakdown ?? [];
  const roomLabel = estimate.room_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const summary = {
    materials:   estimate.subtotal_materials ?? 0,
    labor:       estimate.subtotal_labor ?? 0,
    permits:     estimate.permits ?? 0,
    contingency: estimate.contingency ?? 0,
    total:       estimate.total_estimate ?? 0,
    low:         estimate.estimate_range?.low ?? 0,
    high:        estimate.estimate_range?.high ?? 0,
  };

  return (
    <View style={doc.page}>
      {/* Letterhead */}
      <View style={doc.letterhead}>
        <LogoMark size={40} fontSize={20} />
        <View style={doc.letterheadText}>
          <Text style={doc.companyName}>{CONTRACTOR.company}</Text>
          <Text style={doc.companyMeta}>Lic. {CONTRACTOR.license}</Text>
          <Text style={doc.companyMeta}>{CONTRACTOR.phone}  ·  {CONTRACTOR.email}</Text>
        </View>
      </View>
      <View style={doc.divider} />

      {/* Proposal header */}
      <View style={doc.section}>
        <View style={doc.proposalTitleRow}>
          <Text style={doc.proposalTitle}>PROPOSAL</Text>
          <Text style={doc.proposalId}>#{propId}</Text>
        </View>
        <View style={doc.metaGrid}>
          {[
            { label: 'Project',      value: `${roomLabel} Remodel` },
            { label: 'Date',         value: fmtDate() },
            { label: 'Prepared for', value: client.name },
            { label: 'Address',      value: client.address || '—' },
            { label: 'Valid for',    value: `${VALID_DAYS} days` },
            { label: 'Timeline',     value: `~${estimate.timeline_estimate_weeks ?? 4} weeks` },
          ].map(({ label, value }) => (
            <View key={label} style={doc.metaItem}>
              <Text style={doc.metaLabel}>{label}</Text>
              <Text style={doc.metaValue}>{value}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={doc.divider} />

      {/* Scope of work */}
      <View style={doc.section}>
        <Text style={doc.tableTitle}>SCOPE OF WORK</Text>
        <View style={doc.tableHeader}>
          <Text style={[doc.tableHeaderCell, { flex: 1 }]}>Description</Text>
          <Text style={[doc.tableHeaderCell, { width: 72, textAlign: 'right' }]}>Amount</Text>
        </View>
        {lineItems.length > 0 ? lineItems.map((item, i) => (
          <View key={item.item + i} style={[doc.tableRow, i % 2 === 1 && doc.tableRowAlt]}>
            <View style={{ flex: 1 }}>
              <Text style={doc.tableCell}>{item.item}</Text>
              {!!item.scope && <Text style={[doc.tableCell, { fontSize: 10, color: '#94A3B8' }]}>{item.scope}</Text>}
            </View>
            <Text style={[doc.tableCell, doc.tableCellRight, { width: 72 }]}>{fmt(item.total)}</Text>
          </View>
        )) : (
          <Text style={[doc.tableCell, { padding: 8, color: '#94A3B8' }]}>No line items available.</Text>
        )}
      </View>
      <View style={doc.divider} />

      {/* Cost summary */}
      <View style={doc.section}>
        <Text style={doc.tableTitle}>COST SUMMARY</Text>
        {[
          { label: 'Materials',      value: summary.materials   },
          { label: 'Labor',          value: summary.labor       },
          { label: 'Permits & fees', value: summary.permits     },
          { label: 'Contingency',    value: summary.contingency },
        ].map(({ label, value }) => (
          <View key={label} style={doc.summaryRow}>
            <Text style={doc.summaryLabel}>{label}</Text>
            <Text style={doc.summaryValue}>{fmt(value)}</Text>
          </View>
        ))}
        <View style={doc.totalRow}>
          <Text style={doc.totalLabel}>TOTAL ESTIMATE</Text>
          <Text style={doc.totalValue}>{fmt(summary.total)}</Text>
        </View>
        {summary.low > 0 && summary.high > 0 && (
          <Text style={doc.rangeNote}>
            Estimated range: {fmt(summary.low)} – {fmt(summary.high)}
          </Text>
        )}
      </View>
      <View style={doc.divider} />

      {/* Payment terms */}
      <View style={doc.section}>
        <Text style={doc.tableTitle}>PAYMENT TERMS</Text>
        <Text style={doc.paymentText}>{PAYMENT_TERMS}</Text>
      </View>
      <View style={doc.divider} />

      {/* Signatures */}
      <View style={doc.sigSection}>
        <View style={doc.sigBlock}>
          <View style={doc.sigLine} />
          <Text style={doc.sigName}>{CONTRACTOR.name}</Text>
          <Text style={doc.sigRole}>Contractor</Text>
        </View>
        <View style={doc.sigBlock}>
          <View style={doc.sigLine} />
          <Text style={doc.sigName}>{client.name}</Text>
          <Text style={doc.sigRole}>Client</Text>
        </View>
      </View>

      <Text style={doc.footer}>Generated by Groundwork · Camera-to-Estimate™</Text>
    </View>
  );
}

// ─── Action button ────────────────────────────────────────────────────────────
function ActionBtn({
  icon, label, sublabel, onPress, primary = false, loading = false, disabled = false,
}: {
  icon: string; label: string; sublabel?: string; onPress: () => void;
  primary?: boolean; loading?: boolean; disabled?: boolean;
}) {
  return (
    <Pressable
      style={({ pressed }) => [
        styles.actionBtn,
        primary && styles.actionBtnPrimary,
        (pressed || disabled) && styles.actionBtnPressed,
      ]}
      onPress={onPress}
      disabled={disabled || loading}
    >
      {loading ? (
        <ActivityIndicator color={Colors.primary} style={{ width: 32 }} />
      ) : (
        <Text style={styles.actionBtnIcon}>{icon}</Text>
      )}
      <View style={styles.actionBtnTextWrap}>
        <Text style={[styles.actionBtnLabel, primary && styles.actionBtnLabelPrimary]}>
          {loading ? 'Generating PDF…' : label}
        </Text>
        {sublabel && !loading && <Text style={styles.actionBtnSublabel}>{sublabel}</Text>}
      </View>
      {!loading && <Text style={styles.actionBtnChevron}>›</Text>}
    </Pressable>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function ProposalScreen() {
  const estimate    = getEstimateResult();
  const jobId       = getEstimateJobId();
  const storedClient = getProjectClient();
  const client = {
    ...FALLBACK_CLIENT,
    ...(storedClient ? { name: storedClient.name, address: storedClient.address } : {}),
  };
  const [pdfLoading, setPdfLoading] = useState(false);

  // Fallback proposal number for preview (no real ID until PDF is generated)
  const propId = `GW-${new Date().getFullYear()}-${Date.now().toString().slice(-4)}`;

  const summary = estimate ? {
    total:  estimate.total_estimate ?? 0,
    low:    estimate.estimate_range?.low ?? 0,
    high:   estimate.estimate_range?.high ?? 0,
    weeks:  estimate.timeline_estimate_weeks ?? 4,
    room:   estimate.room_type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
  } : null;

  const handleShare = async () => {
    if (!summary) return;
    try {
      await Share.share({
        title: `Groundwork Proposal – ${summary.room} Remodel`,
        message:
          `GROUNDWORK PROPOSAL\n${summary.room} Remodel\n\n` +
          `Total Estimate: ${fmt(summary.total)}\nRange: ${fmt(summary.low)} – ${fmt(summary.high)}\n\n` +
          `Payment: ${PAYMENT_TERMS}\nValid for ${VALID_DAYS} days.\n\n` +
          `Prepared by ${CONTRACTOR.company} · ${CONTRACTOR.phone}`,
      });
    } catch {}
  };

  const handleText = () => {
    if (!summary) return;
    const body = encodeURIComponent(
      `Hi, I've put together a proposal for your ${summary.room} remodel. ` +
      `Total estimate: ${fmt(summary.total)} (range ${fmt(summary.low)}–${fmt(summary.high)}). ` +
      `Valid for ${VALID_DAYS} days. — ${CONTRACTOR.name}, ${CONTRACTOR.company}`
    );
    Linking.openURL(`sms:${client.phone || ''}?body=${body}`).catch(() =>
      Alert.alert('Unable to open Messages')
    );
  };

  const handleEmail = () => {
    if (!summary) return;
    const subject = encodeURIComponent(`Proposal: ${summary.room} Remodel – ${fmt(summary.total)}`);
    const body = encodeURIComponent(
      `Hi,\n\nPlease find your project proposal below.\n\n` +
      `Project: ${summary.room} Remodel\nTotal Estimate: ${fmt(summary.total)}\n` +
      `Range: ${fmt(summary.low)} – ${fmt(summary.high)}\n` +
      `Payment: ${PAYMENT_TERMS}\nValid for: ${VALID_DAYS} days\n\n` +
      `Best,\n${CONTRACTOR.name}\n${CONTRACTOR.company}\n${CONTRACTOR.phone}`
    );
    Linking.openURL(`mailto:${client.email || ''}?subject=${subject}&body=${body}`).catch(() =>
      Alert.alert('Unable to open Mail')
    );
  };

  const handleDownload = async () => {
    if (!jobId) {
      Alert.alert('No Estimate', 'Complete an analysis first to generate a proposal PDF.');
      return;
    }
    try {
      setPdfLoading(true);
      const result = await groundworkApi.createProposal({
        estimate_job_id: jobId,
        contractor: CONTRACTOR,
        client: client,
        payment_terms: PAYMENT_TERMS,
        valid_days: VALID_DAYS,
      });
      if (result.pdf_url) {
        await Linking.openURL(result.pdf_url);
      } else {
        Alert.alert('PDF Ready', `Proposal ID: ${result.proposal_id}. PDF URL unavailable (S3 not configured).`);
      }
    } catch (err: any) {
      Alert.alert('PDF Failed', err?.message ?? 'Could not generate PDF. Try again.');
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <Animated.View entering={FadeIn.duration(300)}>
          <ScreenHeader title="Proposal" onBack={() => router.back()} />
        </Animated.View>

        {/* Ready badge */}
        <Animated.View entering={FadeInDown.delay(80).duration(350)} style={styles.readyBadge}>
          <Text style={styles.readyBadgeText}>✓</Text>
          <View>
            <Text style={styles.readyTitle}>Proposal Ready</Text>
            <Text style={styles.readySub}>
              {summary ? `${summary.room} · ${fmt(summary.total)}` : 'Review and send to client'}
            </Text>
          </View>
        </Animated.View>

        {/* Document preview */}
        <Animated.View entering={FadeInDown.delay(160).duration(400)} style={styles.docWrap}>
          {estimate ? (
            <ProposalDocument estimate={estimate} propId={propId} client={client} />
          ) : (
            <View style={[doc.page, { alignItems: 'center', paddingVertical: 32 }]}>
              <Text style={{ color: '#94A3B8', fontSize: 14 }}>No estimate data — run an analysis first.</Text>
            </View>
          )}
        </Animated.View>

        {/* Actions */}
        <Animated.View entering={FadeInDown.delay(280).duration(400)}>
          <SectionLabel style={styles.sectionPad}>Send to Client</SectionLabel>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(320).duration(400)} style={styles.actionsCard}>
          <ActionBtn icon="💬" label="Text Client"   sublabel={client.phone || 'Add client phone'} onPress={handleText}  primary />
          <View style={styles.actionDivider} />
          <ActionBtn icon="✉️" label="Email Client"  sublabel={client.email || 'Add client email'} onPress={handleEmail} />
          <View style={styles.actionDivider} />
          <ActionBtn
            icon="⬇️" label="Download PDF"
            sublabel="Generate & save to Files"
            onPress={handleDownload}
            loading={pdfLoading}
            disabled={!jobId}
          />
          <View style={styles.actionDivider} />
          <ActionBtn icon="↗️" label="Share"         sublabel="AirDrop, Messages, more…" onPress={handleShare} />
        </Animated.View>

        {/* Start new */}
        <Animated.View entering={FadeInDown.delay(420).duration(400)}>
          <Pressable style={styles.newEstimateBtn} onPress={() => router.push('/')}>
            <Text style={styles.newEstimateBtnText}>+ Start New Estimate</Text>
          </Pressable>
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Document styles (white paper look) ──────────────────────────────────────
const doc = StyleSheet.create({
  page: { backgroundColor: '#FFFFFF', borderRadius: 12, padding: 20, gap: 0 },
  letterhead: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingBottom: 16 },
  letterheadText: { gap: 1 },
  companyName: { fontSize: 14, fontWeight: '800', color: '#0F172A' },
  companyMeta: { fontSize: 11, color: '#64748B' },
  divider: { height: 1, backgroundColor: '#E2E8F0', marginVertical: 14 },
  section: { gap: 10 },
  proposalTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  proposalTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A', letterSpacing: 1 },
  proposalId: { fontSize: 12, color: '#94A3B8' },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  metaItem: { width: '47%', gap: 2 },
  metaLabel: { fontSize: 10, fontWeight: '700', color: '#94A3B8', letterSpacing: 0.8 },
  metaValue: { fontSize: 13, color: '#0F172A', fontWeight: '500' },
  tableTitle: { fontSize: 11, fontWeight: '700', color: '#94A3B8', letterSpacing: 1, marginBottom: 6 },
  tableHeader: {
    flexDirection: 'row', backgroundColor: '#F8FAFC',
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: 6,
  },
  tableHeaderCell: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.5 },
  tableRow: { flexDirection: 'row', paddingHorizontal: 8, paddingVertical: 7 },
  tableRowAlt: { backgroundColor: '#F8FAFC', borderRadius: 4 },
  tableCell: { fontSize: 13, color: '#334155' },
  tableCellRight: { fontWeight: '600', color: '#0F172A', textAlign: 'right' },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  summaryLabel: { fontSize: 13, color: '#64748B' },
  summaryValue: { fontSize: 13, color: '#334155', fontWeight: '500' },
  totalRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    borderTopWidth: 1, borderTopColor: '#E2E8F0',
    paddingTop: 8, marginTop: 4,
  },
  totalLabel: { fontSize: 14, fontWeight: '800', color: '#0F172A', letterSpacing: 0.5 },
  totalValue: { fontSize: 18, fontWeight: '800', color: '#F97316' },
  rangeNote: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  paymentText: { fontSize: 13, color: '#334155', lineHeight: 20 },
  sigSection: { flexDirection: 'row', gap: 20, paddingTop: 4 },
  sigBlock: { flex: 1, gap: 6 },
  sigLine: { height: 1, backgroundColor: '#CBD5E1' },
  sigName: { fontSize: 12, fontWeight: '600', color: '#334155' },
  sigRole: { fontSize: 11, color: '#94A3B8' },
  footer: { fontSize: 10, color: '#CBD5E1', textAlign: 'center', marginTop: 16, letterSpacing: 0.3 },
});

// ─── App styles (dark theme) ──────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 32, gap: 14 },
  sectionPad: { paddingHorizontal: 2 },

  readyBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: Colors.successBg,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.success + '40',
    padding: 16,
  },
  readyBadgeText: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: Colors.success,
    textAlign: 'center', lineHeight: 36,
    fontSize: 18, fontWeight: '700', color: Colors.white,
    overflow: 'hidden',
  },
  readyTitle: { fontSize: 16, fontWeight: '700', color: Colors.success },
  readySub: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },

  docWrap: {
    borderRadius: 16, overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4, shadowRadius: 24,
    elevation: 12,
  },

  actionsCard: {
    backgroundColor: Colors.surface,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    overflow: 'hidden',
  },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 18, paddingVertical: 16, gap: 14,
  },
  actionBtnPrimary: { backgroundColor: Colors.primary + '15' },
  actionBtnPressed: { backgroundColor: Colors.surfaceRaised },
  actionBtnIcon: { fontSize: 22, width: 32, textAlign: 'center' },
  actionBtnTextWrap: { flex: 1, gap: 2 },
  actionBtnLabel: { fontSize: 15, fontWeight: '600', color: Colors.text },
  actionBtnLabelPrimary: { color: Colors.primary },
  actionBtnSublabel: { fontSize: 12, color: Colors.textSubtle },
  actionBtnChevron: { fontSize: 20, color: Colors.textSubtle, fontWeight: '300' },
  actionDivider: { height: 1, backgroundColor: Colors.border, marginLeft: 64 },

  newEstimateBtn: {
    alignItems: 'center', paddingVertical: 16,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  newEstimateBtnText: { fontSize: 15, fontWeight: '600', color: Colors.textMuted },
});
