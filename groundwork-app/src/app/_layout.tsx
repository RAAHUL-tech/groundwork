import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Colors } from '@/constants/colors';

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: Colors.background },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="capture" />
        <Stack.Screen name="camera" />
        <Stack.Screen name="scanning" />
        <Stack.Screen name="result" />
        <Stack.Screen name="estimate" />
        <Stack.Screen name="proposal" />
        <Stack.Screen name="projects" />
        <Stack.Screen name="project/[id]" />
      </Stack>
    </>
  );
}
