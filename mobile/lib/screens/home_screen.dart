import 'package:flutter/material.dart';
import 'package:swmm_mobile/services/api_service.dart';
import 'package:swmm_mobile/services/storage_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String networkMode = 'online';
  String serverStatus = 'checking';
  Map<String, dynamic>? serverInfo;
  int pendingCount = 0;

  @override
  void initState() {
    super.initState();
    loadSettings();
  }

  Future<void> loadSettings() async {
    try {
      final mode = await storageService.getNetworkMode();
      setState(() => networkMode = mode);
      
      final changes = await storageService.getPendingChanges();
      setState(() => pendingCount = changes.length);

      if (mode == 'online') {
        checkServerStatus();
      } else {
        setState(() => serverStatus = 'offline');
      }
    } catch (e) {
      debugPrint(e.toString());
    }
  }

  Future<void> toggleNetworkMode(bool value) async {
    final newMode = value ? 'online' : 'offline';
    setState(() => networkMode = newMode);
    await storageService.setNetworkMode(newMode);
    
    if (newMode == 'online') {
      checkServerStatus();
    } else {
      setState(() {
        serverStatus = 'offline';
        serverInfo = null;
      });
    }
  }

  Future<void> checkServerStatus() async {
    try {
      setState(() => serverStatus = 'checking');
      final healthData = await HealthService().checkHealth();
      setState(() {
        serverStatus = 'online';
        serverInfo = healthData;
      });
    } catch (error) {
      setState(() => serverStatus = 'offline');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible de contacter le serveur FastAPI')),
        );
      }
    }
  }

  Color getStatusColor() {
    if (networkMode == 'offline') return const Color(0xFFe67e22);
    switch (serverStatus) {
      case 'online': return const Color(0xFF27ae60);
      case 'offline': return const Color(0xFFe74c3c);
      case 'checking': return const Color(0xFFf39c12);
      default: return const Color(0xFF95a5a6);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            Container(
              color: const Color(0xFF16213e),
              padding: const EdgeInsets.all(24),
              child: const Column(
                children: [
                  Text(
                    'SWMM Platform Mobile',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Outil terrain d\'assainissement',
                    style: TextStyle(
                      fontSize: 13,
                      color: Color(0xFFbdc3c7),
                    ),
                  ),
                ],
              ),
            ),
            Card(
              margin: const EdgeInsets.all(16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          '🔌 Mode Réseau Simulé',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Switch(
                          value: networkMode == 'online',
                          onChanged: toggleNetworkMode,
                          activeColor: const Color(0xFF2ecc71),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      networkMode == 'online'
                          ? 'Mode connecté : Les données s\'envoient directement au serveur.'
                          : 'Mode hors ligne : Toutes vos observations et incidents sont stockés localement.',
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFF7f8c8d),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Card(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    const Text(
                      'État du système :',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF7f8c8d),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color: getStatusColor(),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      networkMode == 'offline'
                          ? 'Application Hors ligne'
                          : serverStatus == 'online'
                              ? 'Serveur en ligne ✓'
                              : serverStatus == 'offline'
                                  ? 'Serveur injoignable ✗'
                                  : 'Vérification...',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: getStatusColor(),
                      ),
                    ),
                    if (serverInfo != null && networkMode == 'online') ...[
                      const SizedBox(height: 8),
                      const Divider(),
                      Text(
                        'Base DB : ${serverInfo!['database']}',
                        style: const TextStyle(fontSize: 12),
                      ),
                      Text(
                        'Cache Graphe : ${serverInfo!['graph_cache']}',
                        style: const TextStyle(fontSize: 12),
                      ),
                    ],
                    if (networkMode == 'online') ...[
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: checkServerStatus,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF16213e),
                        ),
                        child: const Text(
                          'Actualiser',
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Card(
                    child: InkWell(
                      onTap: () => Navigator.pushNamed(context, '/map'),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '🗺️ Carte & Collecte',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  'Fiches terrain, photos, GPS et signalement d\'incidents',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Color(0xFF7f8c8d),
                                  ),
                                ),
                              ],
                            ),
                            if (pendingCount > 0)
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF2ecc71),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: Text(
                                  '$pendingCount',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: InkWell(
                      onTap: () => Navigator.pushNamed(context, '/sync'),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '🔄 Synchronisation',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  'Synchroniser les données locales vers le bureau d\'études',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Color(0xFF7f8c8d),
                                  ),
                                ),
                              ],
                            ),
                            if (pendingCount > 0)
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFe67e22),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: Text(
                                  '$pendingCount',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Version mobile 1.0.0 -- Dr A. Kellouche',
              style: const TextStyle(
                fontSize: 11,
                color: Color(0xFFa4b0be),
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}