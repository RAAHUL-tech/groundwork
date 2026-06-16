import { View, StyleSheet } from 'react-native';
import { Colors } from '@/constants/colors';

interface ConfidenceBarProps {
  confidence: number;
  color?: string;
  height?: number;
}

export function confidenceColor(conf: number) {
  if (conf >= 0.85) return Colors.success;
  if (conf >= 0.70) return Colors.warning;
  return Colors.error;
}

export function confidenceLabel(conf: number) {
  if (conf >= 0.85) return 'High';
  if (conf >= 0.70) return 'Medium';
  return 'Low';
}

export function ConfidenceBar({ confidence, color, height = 6 }: ConfidenceBarProps) {
  const barColor = color ?? confidenceColor(confidence);
  return (
    <View style={[styles.track, { height }]}>
      <View
        style={[
          styles.fill,
          { width: `${Math.round(confidence * 100)}%` as any, backgroundColor: barColor, height },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flex: 1,
    backgroundColor: Colors.surfaceRaised,
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: {
    borderRadius: 3,
  },
});
