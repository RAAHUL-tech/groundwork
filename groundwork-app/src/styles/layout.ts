import { StyleSheet } from 'react-native';
import { Colors } from '@/constants/colors';

export const Layout = StyleSheet.create({
  // Base containers
  screen: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  screenCentered: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // Scroll content padding (standard page inset)
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 32,
    gap: 14,
  },

  // Flex helpers
  flex1: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center' },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  center: { alignItems: 'center', justifyContent: 'center' },

  // Dividers
  divider: {
    height: 1,
    backgroundColor: Colors.border,
  },
  dividerInset: {
    height: 1,
    backgroundColor: Colors.border,
    marginLeft: 20,
  },

  // Spacing helpers
  px20: { paddingHorizontal: 20 },
  py16: { paddingVertical: 16 },

  // Standard screen header row
  screenHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 12,
    paddingBottom: 4,
  },

  // Sticky footer for CTAs
  stickyFooter: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    backgroundColor: Colors.background,
  },
});
