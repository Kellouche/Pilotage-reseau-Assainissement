import 'package:flutter/material.dart';
import 'package:swmm_mobile/services/api_service.dart';
import 'package:swmm_mobile/services/storage_service.dart';
import 'dart:ui';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  String networkMode = 'online';
  String serverStatus = 'checking';
  Map<String, dynamic>? serverInfo;
  int pendingCount = 0;
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    
    loadSettings();
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
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
      if (pendingCount > 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Synchronisation en arrière-plan démarrée ($pendingCount éléments)...')),
        );
        _runBackgroundSync();
      }
    } else {
      setState(() {
        serverStatus = 'offline';
        serverInfo = null;
      });
    }
  }

  Future<void> _runBackgroundSync() async {
    try {
      final pendingChanges = await storageService.getPendingChanges();
      if (pendingChanges.isEmpty) return;
      
      final formattedChanges = pendingChanges.map((change) => ({
        'type': change['type'] == 'incident' ? 'create' : 'update',
        'layer': change['type'] == 'incident'
            ? 'incidents'
            : change['type'] == 'inspection'
                ? 'inspections'
                : '${change['type']}s',
        'feature_id': change['object_id'] ?? '0',
        'changes': change,
      })).toList();

      final result = await syncService.pushChanges('mobile-device-001', formattedChanges);
      await storageService.clearPendingChanges();
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Synchronisation réussie ! (${result['accepted']} envoyés)'),
            backgroundColor: const Color(0xFF10B981),
          ),
        );
        setState(() => pendingCount = 0);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Échec de la synchronisation en arrière-plan'),
            backgroundColor: Color(0xFFEF4444),
          ),
        );
      }
    }
  }

  Future<void> checkServerStatus() async {
    try {
      setState(() => serverStatus = 'checking');
      final healthData = await healthService.checkHealth();
      setState(() {
        serverStatus = 'online';
        serverInfo = healthData;
      });
    } catch (error) {
      setState(() => serverStatus = 'offline');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Impossible de contacter le serveur FastAPI'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  Color getStatusColor() {
    if (networkMode == 'offline') return const Color(0xFFF59E0B); // Amber
    switch (serverStatus) {
      case 'online': return const Color(0xFF10B981); // Emerald
      case 'offline': return const Color(0xFFEF4444); // Red
      case 'checking': return const Color(0xFF3B82F6); // Blue
      default: return const Color(0xFF9CA3AF); // Gray
    }
  }

  Widget _buildGlassCard({required Widget child, EdgeInsetsGeometry? padding}) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.1),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withOpacity(0.2), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 20,
            offset: const Offset(0, 10),
          )
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
          child: Padding(
            padding: padding ?? const EdgeInsets.all(20),
            child: child,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0F172A), // Slate 900
              Color(0xFF1E1B4B), // Indigo 950
              Color(0xFF0F172A), // Slate 900
            ],
          ),
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 40),
                // Header
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.blue.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Text(
                          'BETA',
                          style: TextStyle(
                            color: Colors.blueAccent,
                            fontWeight: FontWeight.bold,
                            fontSize: 12,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'SWMM Platform',
                        style: TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.w800,
                          color: Colors.white,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const Text(
                        'Outil terrain d\'assainissement',
                        style: TextStyle(
                          fontSize: 16,
                          color: Color(0xFF94A3B8), // Slate 400
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 40),

                // Network Mode Card
                _buildGlassCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Icon(Icons.wifi_rounded, color: Colors.white, size: 24),
                              ),
                              const SizedBox(width: 16),
                              const Text(
                                'Mode Connexion',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          ),
                          Switch(
                            value: networkMode == 'online',
                            onChanged: toggleNetworkMode,
                            activeColor: Colors.white,
                            activeTrackColor: const Color(0xFF10B981),
                            inactiveThumbColor: Colors.white,
                            inactiveTrackColor: Colors.white.withOpacity(0.3),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Text(
                        networkMode == 'online'
                            ? 'Mode connecté : Les données s\'envoient directement au serveur central et se synchronisent en temps réel.'
                            : 'Mode hors ligne : Toutes vos observations et incidents sont stockés localement sur cet appareil.',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.white.withOpacity(0.7),
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),

                // Server Status Card
                _buildGlassCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          AnimatedBuilder(
                            animation: _pulseController,
                            builder: (context, child) {
                              return Container(
                                width: 12,
                                height: 12,
                                decoration: BoxDecoration(
                                  color: getStatusColor(),
                                  shape: BoxShape.circle,
                                  boxShadow: [
                                    BoxShadow(
                                      color: getStatusColor().withOpacity(_pulseController.value * 0.6),
                                      blurRadius: 10,
                                      spreadRadius: 2,
                                    )
                                  ],
                                ),
                              );
                            },
                          ),
                          const SizedBox(width: 12),
                          const Text(
                            'État du Système',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          const Spacer(),
                          if (networkMode == 'online')
                            IconButton(
                              icon: const Icon(Icons.refresh, color: Colors.white70),
                              onPressed: checkServerStatus,
                              tooltip: 'Actualiser',
                            )
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        networkMode == 'offline'
                            ? 'Application Hors Ligne'
                            : serverStatus == 'online'
                                ? 'Serveur Opérationnel'
                                : serverStatus == 'offline'
                                    ? 'Serveur Injoignable'
                                    : 'Vérification en cours...',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                          color: getStatusColor(),
                        ),
                      ),
                      if (serverInfo != null && networkMode == 'online') ...[
                        const SizedBox(height: 16),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.black.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _buildInfoRow('Base de données', serverInfo!['database'] ?? 'N/A'),
                              const SizedBox(height: 8),
                              _buildInfoRow('Cache Graphe', serverInfo!['graph_cache'] ?? 'N/A'),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),

                const SizedBox(height: 10),

                // Actions
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Row(
                    children: [
                      Expanded(
                        child: _buildActionCard(
                          title: 'Carte',
                          subtitle: 'Inspection',
                          icon: Icons.map_rounded,
                          color: const Color(0xFF3B82F6),
                          onTap: () => Navigator.pushNamed(context, '/map'),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: _buildActionCard(
                          title: 'Sync',
                          subtitle: pendingCount > 0 ? '$pendingCount en attente' : 'À jour',
                          icon: Icons.sync_rounded,
                          color: pendingCount > 0 ? const Color(0xFFF59E0B) : const Color(0xFF10B981),
                          onTap: () => Navigator.pushNamed(context, '/sync'),
                          showBadge: pendingCount > 0,
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 40),
                Center(
                  child: Text(
                    'Version 1.1.0 • Design Premium',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withOpacity(0.3),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 13),
        ),
        Text(
          value,
          style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  Widget _buildActionCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
    bool showBadge = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withOpacity(0.2), width: 1.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Icon(icon, color: color, size: 28),
                ),
                if (showBadge)
                  Container(
                    width: 12,
                    height: 12,
                    decoration: const BoxDecoration(
                      color: Color(0xFFEF4444),
                      shape: BoxShape.circle,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 20),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.white.withOpacity(0.6),
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}