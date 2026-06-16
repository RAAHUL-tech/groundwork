import { View, Text, StyleSheet } from 'react-native';

interface BadgeProps {
  label: string;
  color: string;
  size?: 'sm' | 'md';
}

export function Badge({ label, color, size = 'md' }: BadgeProps) {
  const isSmall = size === 'sm';
  return (
    <View style={[
      styles.wrap,
      { backgroundColor: color + '22', borderColor: color + '55' },
      isSmall && styles.wrapSm,
    ]}>
      <Text style={[styles.text, { color }, isSmall && styles.textSm]}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 5,
    alignSelf: 'flex-start',
  },
  wrapSm: {
    borderRadius: 7,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  text: {
    fontSize: 13,
    fontWeight: '700',
  },
  textSm: {
    fontSize: 11,
  },
});
