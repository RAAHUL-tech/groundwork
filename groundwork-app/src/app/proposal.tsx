import { ScrollView, StyleSheet, Text, View, Pressable, Share, Linking, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeIn, FadeInDown, FadeInUp } from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { ScreenHeader, SectionLabel, LogoMark } from '@/components';

// ─── Mock proposal data ───────────────────────────────────────────────────────
const CONTRACTOR = {
  name: 'Mike Torres',
  company: 'Torres Construction LLC',
  license: 'CA-GC-889234',
  phone: '714-555-0192',
  email: 'mike@torresconstruction.com',
};

const CLIENT = {
  name: 'Sarah Johnson',
  address: '123 Oak St, Fullerton CA 92831',
  phone: '714-555-0844',
  email: 'sarah.johnson@email.com',
};

const PROJECT = {
  title: 'Kitchen Remodel',
  date: 'June 15, 2026',
  validDays: 30,
  paymentTerms: '50% deposit due at signing, 50% on completion',
  timeline: '~4 weeks',
  proposalId: 'GW-2026-0047',
};

const LINE_ITEMS = [
  { label: 'Cabinet replacement',   total: 4532 },
  { label: 'Quartz countertops',    total: 3520 },
  { label: 'LVP flooring',          total: 1785 },
  { label: 'Sink + faucet',         total: 670  },
  { label: 'Interior painting',     total: 1440 },
];

const SUMMARY = {
  materials: 8160, labor: 4865, permits: 1220, contingency: 1425,
  total: 15670, low: 13320, high: 18804,
};

function fmt(n: number) { return '$' + n.toLocaleString(); }

// ─── Document preview ─────────────────────────────────────────────────────────
function ProposalDocument() {
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
          <Text style={doc.proposalId}>#{PROJECT.proposalId}</Text>
        </View>
        <View style={doc.metaGrid}>
          {[
            { label: 'Project',      value: PROJECT.title },
            { label: 'Date',         value: PROJECT.date },
            { label: 'Prepared for', value: CLIENT.name },
            { label: 'Address',      value: CLIENT.address },
            { label: 'Valid for',    value: `${PROJECT.validDays} days` },
            { label: 'Timeline',     value: PROJECT.timeline },
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
          <Text style={doc.tableHeaderCell}>Amount</Text>
        </View>
        {LINE_ITEMS.map((item, i) => (
          <View key={item.label} style={[doc.tableRow, i % 2 === 1 && doc.tableRowAlt]}>
            <Text style={[doc.tableCell, { flex: 1 }]}>{item.label}</Text>
            <Text style={[doc.tableCell, doc.tableCellRight]}>{fmt(item.total)}</Text>
          </View>
        ))}
      </View>

      <View style={doc.divider} />

      {/* Cost summary */}
      <View style={doc.section}>
        <Text style={doc.tableTitle}>COST SUMMARY</Text>
        {[
          { label: 'Materials',      value: SUMMARY.materials   },
          { label: 'Labor',          value: SUMMARY.labor       },
          { label: 'Permits & fees', value: SUMMARY.permits     },
          { label: 'Contingency',    value: SUMMARY.contingency },
        ].map(({ label, value }) => (
          <View key={label} style={doc.summaryRow}>
            <Text style={doc.summaryLabel}>{label}</Text>
            <Text style={doc.summaryValue}>{fmt(value)}</Text>
          </View>
        ))}
        <View style={doc.totalRow}>
          <Text style={doc.totalLabel}>TOTAL ESTIMATE</Text>
          <Text style={doc.totalValue}>{fmt(SUMMARY.total)}</Text>
        </View>
        <Text style={doc.rangeNote}>
          Estimated range: {fmt(SUMMARY.low)} – {fmt(SUMMARY.high)}
        </Text>
      </View>

      <View style={doc.divider} />

      {/* Payment terms */}
      <View style={doc.section}>
        <Text style={doc.tableTitle}>PAYMENT TERMS</Text>
        <Text style={doc.paymentText}>{PROJECT.paymentTerms}</Text>
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
          <Text style={doc.sigName}>{CLIENT.name}</Text>
          <Text style={doc.sigRole}>Client</Text>
        </View>
      </View>

      <Text style={doc.footer}>Generated by Groundwork · Camera-to-Estimate™</Text>
    </View>
  );
}

// ─── Action button ────────────────────────────────────────────────────────────
function ActionBtn({
  icon, label, sublabel, onPress, primary = false,
}: {
  icon: string; label: string; sublabel?: string; onPress: () => void; primary?: boolean;
}) {
  return (
    <Pressable
      style={({ pressed }) => [
        styles.actionBtn,
        primary && styles.actionBtnPrimary,
        pressed && styles.actionBtnPressed,
      ]}
      onPress={onPress}
    >
      <Text style={styles.actionBtnIcon}>{icon}</Text>
      <View style={styles.actionBtnTextWrap}>
        <Text style={[styles.actionBtnLabel, primary && styles.actionBtnLabelPrimary]}>
          {label}
        </Text>
        {sublabel && <Text style={styles.actionBtnSublabel}>{sublabel}</Text>}
      </View>
      <Text style={styles.actionBtnChevron}>›</Text>
    </Pressable>
  );
}

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function ProposalScreen() {
  const handleShare = async () => {
    try {
      await Share.share({
        title: `Proposal – ${PROJECT.title}`,
        message:
          `GROUNDWORK PROPOSAL\n${PROJECT.title} for ${CLIENT.name}\n${CLIENT.address}\n\n` +
          `Total Estimate: ${fmt(SUMMARY.total)}\nRange: ${fmt(SUMMARY.low)} – ${fmt(SUMMARY.high)}\n\n` +
          `Payment: ${PROJECT.paymentTerms}\nValid for ${PROJECT.validDays} days.\n\n` +
          `Prepared by ${CONTRACTOR.company} · ${CONTRACTOR.phone}`,
      });
    } catch {}
  };

  const handleText = () => {
    const body = encodeURIComponent(
      `Hi ${CLIENT.name.split(' ')[0]}, I've put together a proposal for your ${PROJECT.title}. ` +
      `Total estimate: ${fmt(SUMMARY.total)} (range ${fmt(SUMMARY.low)}–${fmt(SUMMARY.high)}). ` +
      `Valid for ${PROJECT.validDays} days. — ${CONTRACTOR.name}, ${CONTRACTOR.company}`
    );
    Linking.openURL(`sms:${CLIENT.phone}?body=${body}`).catch(() =>
      Alert.alert('Unable to open Messages')
    );
  };

  const handleEmail = () => {
    const subject = encodeURIComponent(`Proposal: ${PROJECT.title} – ${fmt(SUMMARY.total)}`);
    const body = encodeURIComponent(
      `Hi ${CLIENT.name.split(' ')[0]},\n\nPlease find your project proposal attached below.\n\n` +
      `Project: ${PROJECT.title}\nTotal Estimate: ${fmt(SUMMARY.total)}\n` +
      `Range: ${fmt(SUMMARY.low)} – ${fmt(SUMMARY.high)}\n` +
      `Payment: ${PROJECT.paymentTerms}\nValid for: ${PROJECT.validDays} days\n\n` +
      `Best,\n${CONTRACTOR.name}\n${CONTRACTOR.company}\n${CONTRACTOR.phone}`
    );
    Linking.openURL(`mailto:${CLIENT.email}?subject=${subject}&body=${body}`).catch(() =>
      Alert.alert('Unable to open Mail')
    );
  };

  const handleDownload = () => {
    Alert.alert(
      'PDF Generation',
      'PDF export will be available once connected to the Groundwork backend.',
      [{ text: 'OK' }]
    );
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
            <Text style={styles.readySub}>Review and send to {CLIENT.name}</Text>
          </View>
        </Animated.View>

        {/* Document preview */}
        <Animated.View entering={FadeInDown.delay(160).duration(400)} style={styles.docWrap}>
          <ProposalDocument />
        </Animated.View>

        {/* Actions */}
        <Animated.View entering={FadeInDown.delay(280).duration(400)}>
          <SectionLabel style={styles.sectionPad}>Send to Client</SectionLabel>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(320).duration(400)} style={styles.actionsCard}>
          <ActionBtn icon="💬" label="Text Client"    sublabel={CLIENT.phone}  onPress={handleText}     primary />
          <View style={styles.actionDivider} />
          <ActionBtn icon="✉️" label="Email Client"   sublabel={CLIENT.email}  onPress={handleEmail} />
          <View style={styles.actionDivider} />
          <ActionBtn icon="⬇️" label="Download PDF"   sublabel="Save to Files" onPress={handleDownload} />
          <View style={styles.actionDivider} />
          <ActionBtn icon="↗️" label="Share"           sublabel="AirDrop, Messages, more…" onPress={handleShare} />
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
  tableCellRight: { fontWeight: '600', color: '#0F172A', textAlign: 'right', minWidth: 64 },
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

  // Ready badge
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

  // Document wrapper
  docWrap: {
    borderRadius: 16, overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4, shadowRadius: 24,
    elevation: 12,
  },

  // Actions
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

  // New estimate
  newEstimateBtn: {
    alignItems: 'center', paddingVertical: 16,
    borderRadius: 16, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  newEstimateBtnText: { fontSize: 15, fontWeight: '600', color: Colors.textMuted },
});
