import { Colors } from '@/constants/colors';

// Plain objects (not StyleSheet.create) so they compose freely with local styles.
export const Typography = {
  displayLarge: {
    fontSize: 48,
    fontWeight: '800' as const,
    color: Colors.text,
    letterSpacing: -1,
    lineHeight: 54,
  },
  displayMedium: {
    fontSize: 36,
    fontWeight: '800' as const,
    color: Colors.text,
    letterSpacing: -0.5,
  },
  titleLarge: {
    fontSize: 22,
    fontWeight: '700' as const,
    color: Colors.text,
  },
  titleMedium: {
    fontSize: 17,
    fontWeight: '700' as const,
    color: Colors.text,
  },
  titleSmall: {
    fontSize: 15,
    fontWeight: '700' as const,
    color: Colors.text,
  },
  body: {
    fontSize: 15,
    color: Colors.text,
    lineHeight: 22,
  },
  bodyMuted: {
    fontSize: 15,
    color: Colors.textMuted,
    lineHeight: 22,
  },
  bodySmall: {
    fontSize: 13,
    color: Colors.textMuted,
    lineHeight: 19,
  },
  caption: {
    fontSize: 12,
    color: Colors.textSubtle,
  },
  captionBold: {
    fontSize: 12,
    fontWeight: '600' as const,
    color: Colors.textSubtle,
  },
  // Used for all-caps section headers throughout the app
  sectionLabel: {
    fontSize: 11,
    fontWeight: '700' as const,
    color: Colors.textSubtle,
    letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
  },
  brand: {
    fontSize: 15,
    fontWeight: '800' as const,
    color: Colors.text,
    letterSpacing: 2,
  },
};
