import 'package:flutter/material.dart';

void main() {
  runApp(const SwmmApp());
}

class SwmmApp extends StatelessWidget {
  const SwmmApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SWMM Mobile Test',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String networkMode = 'online';
  int pendingCount = 3;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SWMM Platform Mobile')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Card(
              child: ListTile(
                title: const Text('État du système'),
                trailing: CircleAvatar(
                  backgroundColor: networkMode == 'online' ? Colors.green : Colors.orange,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: InkWell(
                onTap: () {},
                child: ListTile(
                  leading: const Icon(Icons.map),
                  title: const Text('Carte & Collecte'),
                  trailing: pendingCount > 0
                      ? CircleAvatar(
                          backgroundColor: Colors.green,
                          child: Text('$pendingCount'),
                        )
                      : null,
                ),
              ),
            ),
            Card(
              child: InkWell(
                onTap: () {},
                child: const ListTile(
                  leading: Icon(Icons.sync),
                  title: Text('Synchronisation'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}