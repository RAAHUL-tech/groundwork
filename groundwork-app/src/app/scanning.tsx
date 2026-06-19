import { useEffect, useState, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  withDelay,
  Easing,
  FadeInDown,
  FadeIn,
} from 'react-native-reanimated';
import { Colors } from '@/constants/colors';
import { LogoMark } from '@/components';
import { groundworkApi } from '@/services/api';
import { setEstimateResult, setEstimateJobId } from '@/services/estimateStore';

type StepStatus = 'pending' | 'active' | 'done';

interface Step {
  id: number;
  label: string;
  detail: string;
  durationMs: number;
}

const STEPS: Step[] = [
  { id: 1, label: 'Classifying room type',        detail: 'Reading scene with Claude Vision',    durationMs: 4000 },
  { id: 2, label: 'Detecting objects & surfaces',  detail: 'Running YOLOv8 object detection',     durationMs: 5000 },
  { id: 3, label: 'Estimating quantities',         detail: 'Measuring linear ft & sq ft',         durationMs: 4000 },
  { id: 4, label: 'Pulling live pricing',          detail: 'Fetching Home Depot material costs',  durationMs: 6000 },
  { id: 5, label: 'Generating estimate',           detail: 'Applying labor rates & markup',       durationMs: 5000 },
];

// Total time for cosmetic step cycling (~24s). Kept separate from progress bar timing.
const TOTAL_MS = STEPS.reduce((sum, s) => sum + s.durationMs, 0);

// Asymptotic progress: approaches 95% but slows naturally — never hard-freezes.
// Formula: 0.95 * (1 - e^(-t / TIME_CONSTANT))
// At 10s ≈ 42%, 20s ≈ 65%, 35s ≈ 80%, 60s ≈ 91%
const PROGRESS_TIME_CONSTANT = 25_000;

function PulsingRing({ delay = 0, size = 160, color = Colors.primary }: { delay?: number; size?: number; color?: string }) {
  const scale = useSharedValue(1);
  const opacity = useSharedValue(0.6);

  useEffect(() => {
    scale.value = withDelay(delay, withRepeat(
      withSequence(
        withTiming(1.4, { duration: 1200, easing: Easing.out(Easing.ease) }),
        withTiming(1,   { duration: 1200, easing: Easing.in(Easing.ease) }),
      ), -1, false
    ));
    opacity.value = withDelay(delay, withRepeat(
      withSequence(
        withTiming(0, { duration: 1200, easing: Easing.out(Easing.ease) }),
        withTiming(0.6, { duration: 0 }),
      ), -1, false
    ));
  }, []);

  const style = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));

  return (
    <Animated.View
      style={[{
        position: 'absolute',
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: 2,
        borderColor: color,
      }, style]}
    />
  );
}

function SpinningArc() {
  const rotation = useSharedValue(0);

  useEffect(() => {
    rotation.value = withRepeat(
      withTiming(360, { duration: 1800, easing: Easing.linear }),
      -1, false
    );
  }, []);

  const style = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  return (
    <Animated.View style={[styles.spinningArc, style]}>
      <View style={styles.arcSegment} />
    </Animated.View>
  );
}

function StepRow({ step, status, index }: { step: Step; status: StepStatus; index: number }) {
  const dotScale = useSharedValue(1);

  useEffect(() => {
    if (status === 'active') {
      dotScale.value = withRepeat(
        withSequence(
          withTiming(1.4, { duration: 500 }),
          withTiming(1,   { duration: 500 }),
        ), -1, true
      );
    } else {
      dotScale.value = 1;
    }
  }, [status]);

  const dotStyle = useAnimatedStyle(() => ({
    transform: [{ scale: dotScale.value }],
  }));

  if (status === 'pending') return null;

  return (
    <Animated.View
      entering={FadeInDown.delay(index * 60).duration(300).springify()}
      style={styles.stepRow}
    >
      <Animated.View style={[styles.stepDot,
        status === 'done'   && styles.stepDotDone,
        status === 'active' && styles.stepDotActive,
        dotStyle,
      ]}>
        {status === 'done' && <Text style={styles.stepDotCheck}>✓</Text>}
        {status === 'active' && <View style={styles.stepDotInner} />}
      </Animated.View>

      <View style={styles.stepText}>
        <Text style={[styles.stepLabel, status === 'active' && styles.stepLabelActive]}>
          {step.label}
        </Text>
        {status === 'active' && (
          <Text style={styles.stepDetail}>{step.detail}</Text>
        )}
      </View>
    </Animated.View>
  );
}

export default function ScanningScreen() {
  const { captureMode, jobId } = useLocalSearchParams<{ captureMode: string; jobId?: string }>();
  const [activeStep, setActiveStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const progressAnim = useSharedValue(0);
  const elapsed = useRef(0);
  const frameRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigatedRef = useRef(false);

  // Cosmetic animation — always runs regardless of polling
  useEffect(() => {
    const startTime = Date.now();
    const cumulativeDurations = STEPS.map((_, i) =>
      STEPS.slice(0, i + 1).reduce((sum, s) => sum + s.durationMs, 0)
    );

    frameRef.current = setInterval(() => {
      elapsed.current = Date.now() - startTime;
      // Cap at 95% — final 5% reserved for when polling confirms complete
      // Asymptotic when backed by a real job — slows naturally, never hard-freezes at 95%.
      // Linear when in mock/no-job mode so it finishes cleanly.
      const rawPct = jobId
        ? 0.95 * (1 - Math.exp(-elapsed.current / PROGRESS_TIME_CONSTANT))
        : Math.min(elapsed.current / TOTAL_MS, 1);
      setProgress(rawPct);
      progressAnim.value = withTiming(rawPct, { duration: 80 });

      const nextStep = cumulativeDurations.findIndex((d) => elapsed.current < d);
      setActiveStep(nextStep === -1 ? STEPS.length - 1 : nextStep);

      // No jobId → mock mode: navigate after animation finishes
      if (!jobId && elapsed.current >= TOTAL_MS && !navigatedRef.current) {
        navigatedRef.current = true;
        clearInterval(frameRef.current!);
        setTimeout(() => {
          router.push({ pathname: '/result' as any, params: { captureMode } });
        }, 400);
      }
    }, 80);

    return () => { if (frameRef.current) clearInterval(frameRef.current); };
  }, []);

  // Real polling — fires only when we have a jobId
  useEffect(() => {
    if (!jobId) return;

    let pollInterval: ReturnType<typeof setInterval>;
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await groundworkApi.pollStatus(jobId);

        if (cancelled) return;

        if (res.status === 'complete' && res.result) {
          setEstimateResult(res.result);
          setEstimateJobId(jobId);
          if (!navigatedRef.current) {
            navigatedRef.current = true;
            // Snap progress to 100% visually
            setProgress(1);
            progressAnim.value = withTiming(1, { duration: 300 });
            clearInterval(pollInterval);
            setTimeout(() => {
              router.push({ pathname: '/result' as any, params: { captureMode } });
            }, 400);
          }
        } else if (res.status === 'failed') {
          clearInterval(pollInterval);
          if (!navigatedRef.current) {
            navigatedRef.current = true;
            // Navigate anyway — result screen will show mock/error state
            router.push({ pathname: '/result' as any, params: { captureMode } });
          }
        }
      } catch {
        // Network hiccup — keep polling
      }
    };

    // First poll immediately, then every 2 seconds
    poll();
    pollInterval = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      clearInterval(pollInterval);
    };
  }, [jobId]);

  const progressBarStyle = useAnimatedStyle(() => ({
    width: `${progressAnim.value * 100}%`,
  }));

  const pct = Math.round(progress * 100);

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <Animated.View entering={FadeIn.duration(400)} style={styles.header}>
        <LogoMark size={40} fontSize={20} />
        <Text style={styles.headerTitle}>Analyzing your room</Text>
        <Text style={styles.headerSub}>
          {captureMode === 'video' ? 'Processing walkthrough video' : 'Processing photo'}
        </Text>
      </Animated.View>

      {/* Scanner animation */}
      <View style={styles.scannerWrap}>
        <PulsingRing size={200} delay={0}   color={Colors.primary} />
        <PulsingRing size={200} delay={600} color={Colors.primary} />
        <SpinningArc />
        <View style={styles.scannerCore}>
          <Text style={styles.scannerPct}>{pct}%</Text>
          <Text style={styles.scannerLabel}>complete</Text>
        </View>
      </View>

      {/* Progress bar */}
      <View style={styles.progressBarWrap}>
        <Animated.View style={[styles.progressBar, progressBarStyle]} />
      </View>

      {/* Steps */}
      <View style={styles.stepsWrap}>
        {STEPS.map((step, i) => {
          const status: StepStatus =
            i < activeStep ? 'done' : i === activeStep ? 'active' : 'pending';
          return (
            <StepRow key={step.id} step={step} status={status} index={i} />
          );
        })}
      </View>

      {/* Footer hint */}
      <Animated.View entering={FadeIn.delay(300).duration(500)} style={styles.footer}>
        <Text style={styles.footerText}>
          Groundwork checks live Home Depot pricing for every line item
        </Text>
      </Animated.View>
    </SafeAreaView>
  );
}

const SCANNER_SIZE = 160;
const ARC_SIZE = SCANNER_SIZE + 32;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: 'center',
    paddingHorizontal: 24,
  },

  // Header
  header: {
    alignItems: 'center',
    paddingTop: 32,
    paddingBottom: 16,
    gap: 8,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: Colors.text,
    textAlign: 'center',
  },
  headerSub: {
    fontSize: 14,
    color: Colors.textMuted,
  },

  // Scanner
  scannerWrap: {
    width: ARC_SIZE + 40,
    height: ARC_SIZE + 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 24,
  },
  spinningArc: {
    position: 'absolute',
    width: ARC_SIZE,
    height: ARC_SIZE,
    borderRadius: ARC_SIZE / 2,
  },
  arcSegment: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: ARC_SIZE / 2,
    borderWidth: 3,
    borderColor: 'transparent',
    borderTopColor: Colors.primary,
    borderRightColor: Colors.primary,
  },
  scannerCore: {
    width: SCANNER_SIZE,
    height: SCANNER_SIZE,
    borderRadius: SCANNER_SIZE / 2,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  scannerPct: {
    fontSize: 36,
    fontWeight: '800',
    color: Colors.text,
    fontVariant: ['tabular-nums'],
  },
  scannerLabel: {
    fontSize: 13,
    color: Colors.textMuted,
    fontWeight: '500',
  },

  // Progress bar
  progressBarWrap: {
    width: '100%',
    height: 4,
    backgroundColor: Colors.surface,
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 28,
  },
  progressBar: {
    height: 4,
    backgroundColor: Colors.primary,
    borderRadius: 2,
  },

  // Steps
  stepsWrap: { width: '100%', gap: 12 },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  stepDot: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: Colors.surface,
    borderWidth: 2,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  stepDotDone: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  stepDotActive: {
    borderColor: Colors.primary,
    backgroundColor: Colors.background,
  },
  stepDotInner: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.primary,
  },
  stepDotCheck: {
    fontSize: 12,
    color: Colors.white,
    fontWeight: '700',
  },
  stepText: { flex: 1, gap: 2 },
  stepLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.textMuted,
    lineHeight: 22,
  },
  stepLabelActive: { color: Colors.text },
  stepDetail: { fontSize: 12, color: Colors.textSubtle },

  // Footer
  footer: {
    position: 'absolute',
    bottom: 36,
    left: 24,
    right: 24,
    alignItems: 'center',
  },
  footerText: {
    fontSize: 12,
    color: Colors.textSubtle,
    textAlign: 'center',
    lineHeight: 18,
  },
});
