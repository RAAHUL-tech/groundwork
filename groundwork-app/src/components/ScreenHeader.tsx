import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Colors } from '@/constants/colors';
import { Layout } from '@/styles/layout';
import { Typography } from '@/styles/typography';

interface ScreenHeaderProps {
  title: string;
  onBack: () => void;
  right?: React.ReactNode;
}

export function ScreenHeader({ title, onBack, right }: ScreenHeaderProps) {
  return (
    <View style={Layout.screenHeader}>
      <Pressable style={styles.backBtn} onPress={onBack} hitSlop={12}>
        <Text style={styles.backBtnText}>←</Text>
      </Pressable>
      <Text style={styles.title}>{title}</Text>
      <View style={styles.rightSlot}>{right ?? null}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backBtnText: {
    fontSize: 20,
    color: Colors.text,
    fontWeight: '600',
  },
  title: {
    ...Typography.titleMedium,
  },
  rightSlot: {
    width: 40,
    alignItems: 'flex-end',
  },
});
