import { Text, StyleSheet, type TextStyle, type StyleProp } from 'react-native';
import { Typography } from '@/styles/typography';

interface SectionLabelProps {
  children: string;
  style?: StyleProp<TextStyle>;
}

export function SectionLabel({ children, style }: SectionLabelProps) {
  return <Text style={[styles.label, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  label: {
    ...Typography.sectionLabel,
    marginBottom: 8,
  },
});
