/**
 * API base URL.
 *
 * Set EXPO_PUBLIC_API_URL in your .env to override.
 *
 * • iOS Simulator  → localhost resolves to host machine — use http://localhost:5001
 * • Android Emulator → use http://10.0.2.2:5001
 * • Physical device → use your machine's LAN IP, e.g. http://192.168.1.100:5001
 */
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:5001';
