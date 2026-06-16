import { Pressable, View, Text, StyleSheet, type ViewStyle, type StyleProp } from 'react-native';
import { Colors } from '@/constants/colors';

interface PrimaryButtonProps {
  label: string;
  onPress: () => void;
  leftIcon?: string;
  showArrow?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function PrimaryButton({
  label,
  onPress,
  leftIcon,
  showArrow = true,
  disabled = false,
  style,
}: PrimaryButtonProps) {
  return (
    <Pressable
      style={({ pressed }) => [
        styles.btn,
        pressed && styles.btnPressed,
        disabled && styles.btnDisabled,
        style,
      ]}
      onPress={onPress}
      disabled={disabled}
    >
      {leftIcon && (
        <View style={styles.iconWrap}>
          <Text style={styles.iconText}>{leftIcon}</Text>
        </View>
      )}
      <Text style={[styles.label, leftIcon && styles.labelWithIcon]}>{label}</Text>
      {showArrow && <Text style={styles.arrow}>→</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    backgroundColor: Colors.primary,
    borderRadius: 16,
    paddingVertical: 18,
    paddingHorizontal: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    shadowColor: Colors.primary,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 16,
    elevation: 8,
  },
  btnPressed: {
    backgroundColor: Colors.primaryDark,
    shadowOpacity: 0.15,
  },
  btnDisabled: {
    opacity: 0.5,
    shadowOpacity: 0,
    elevation: 0,
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: {
    fontSize: 18,
    color: Colors.white,
    fontWeight: '700',
  },
  label: {
    fontSize: 17,
    fontWeight: '700',
    color: Colors.white,
    textAlign: 'center',
  },
  labelWithIcon: {
    flex: 1,
    fontSize: 18,
  },
  arrow: {
    fontSize: 18,
    color: 'rgba(255,255,255,0.7)',
  },
});
