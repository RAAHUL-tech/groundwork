import { View, Text, StyleSheet } from 'react-native';
import { Colors } from '@/constants/colors';

interface LogoMarkProps {
  size?: number;
  fontSize?: number;
}

export function LogoMark({ size = 44, fontSize = 22 }: LogoMarkProps) {
  const borderRadius = Math.round(size * 0.27);
  return (
    <View style={[styles.wrap, { width: size, height: size, borderRadius }]}>
      <Text style={[styles.letter, { fontSize }]}>G</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  letter: {
    fontWeight: '800',
    color: Colors.white,
    letterSpacing: -0.5,
  },
});
