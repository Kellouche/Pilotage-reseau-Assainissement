import 'package:flutter/material.dart';
import 'package:swmm_mobile/screens/home_screen.dart';
import 'package:swmm_mobile/screens/map_screen.dart';
import 'package:swmm_mobile/screens/sync_screen.dart';

void main() {
  runApp(const SwmmApp());
}

class SwmmApp extends StatelessWidget {
  const SwmmApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SWMM Platform Mobile',
      theme: ThemeData(
        primaryColor: const Color(0xFF16213e),
        scaffoldBackgroundColor: const Color(0xFFf5f6fa),
        appBarTheme: const AppBarTheme(backgroundColor: Color(0xFF16213e)),
      ),
      initialRoute: '/',
      routes: {
        '/': (context) => const HomeScreen(),
        '/map': (context) => const MapScreen(),
        '/sync': (context) => const SyncScreen(),
      },
    );
  }
}