import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { Colors } from '@/constants/colors';
import { LogoMark, EmptyState, SectionLabel, PrimaryButton } from '@/components';

const MOCK_RECENT: {
  id: string;
  room: string;
  address: string;
  total: number;
  date: string;
  confidence: number;
}[] = [];

function EstimateCard({
  room,
  address,
  total,
  date,
  confidence,
}: (typeof MOCK_RECENT)[0]) {
  return (
    <Pressable style={styles.estimateCard}>
      <View style={styles.estimateCardLeft}>
        <Text style={styles.estimateRoom}>{room}</Text>
        <Text style={styles.estimateAddress}>{address}</Text>
        <Text style={styles.estimateDate}>{date}</Text>
      </View>
      <View style={styles.estimateCardRight}>
        <Text style={styles.estimateTotal}>${total.toLocaleString()}</Text>
        <View style={styles.confidenceBadge}>
          <Text style={styles.confidenceText}>{confidence}% conf.</Text>
        </View>
      </View>
    </Pressable>
  );
}

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
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
            AI-powered construction estimates from a single photo — in under 5
            minutes.
          </Text>
        </View>

        {/* Primary CTA */}
        <PrimaryButton
          label="New Estimate"
          leftIcon="＋"
          onPress={() => router.push('/capture' as any)}
          style={styles.ctaButton}
        />

        <Text style={styles.ctaHint}>
          Takes a photo or 15-second walkthrough video
        </Text>

        {/* Divider */}
        <View style={styles.divider} />

        {/* Recent estimates */}
        <View style={styles.section}>
          <SectionLabel style={styles.sectionLabelSpacing}>Recent Estimates</SectionLabel>

          {MOCK_RECENT.length === 0 ? (
            <EmptyState
              icon="🏠"
              title="No estimates yet"
              body={'Tap "New Estimate" above to analyze your first room.'}
            />
          ) : (
            MOCK_RECENT.map((item) => (
              <EstimateCard key={item.id} {...item} />
            ))
          )}
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

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 48 },

  // Header
  header: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 8,
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  brandName: {
    fontSize: 15,
    fontWeight: '800',
    color: Colors.text,
    letterSpacing: 2,
  },
  brandTagline: {
    fontSize: 11,
    color: Colors.textMuted,
    letterSpacing: 0.5,
    marginTop: 1,
  },

  // Hero
  hero: {
    paddingHorizontal: 24,
    paddingTop: 36,
    paddingBottom: 32,
  },
  heroTitle: {
    fontSize: 48,
    fontWeight: '800',
    color: Colors.text,
    lineHeight: 54,
    letterSpacing: -1,
    marginBottom: 16,
  },
  heroSub: {
    fontSize: 16,
    color: Colors.textMuted,
    lineHeight: 24,
    maxWidth: 320,
  },

  // CTA
  ctaButton: { marginHorizontal: 24 },
  ctaHint: {
    marginHorizontal: 24,
    marginTop: 10,
    fontSize: 13,
    color: Colors.textSubtle,
    textAlign: 'center',
  },

  // Divider
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginHorizontal: 24,
    marginTop: 32,
    marginBottom: 28,
  },

  // Section
  section: { paddingHorizontal: 24 },
  sectionLabelSpacing: { marginBottom: 16 },

  // Estimate card
  estimateCard: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  estimateCardLeft: { flex: 1, gap: 3 },
  estimateRoom: { fontSize: 15, fontWeight: '700', color: Colors.text },
  estimateAddress: { fontSize: 13, color: Colors.textMuted },
  estimateDate: { fontSize: 12, color: Colors.textSubtle },
  estimateCardRight: { alignItems: 'flex-end', gap: 6 },
  estimateTotal: { fontSize: 17, fontWeight: '700', color: Colors.primary },
  confidenceBadge: {
    backgroundColor: Colors.successBg,
    borderRadius: 6,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  confidenceText: { fontSize: 11, color: Colors.success, fontWeight: '600' },

  // Feature chips
  featureRow: {
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 24,
    marginTop: 28,
  },
  featureChip: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingVertical: 12,
    alignItems: 'center',
    gap: 6,
  },
  featureChipIcon: { fontSize: 20 },
  featureChipLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
