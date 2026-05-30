import 'package:flutter/material.dart';
import 'package:swmm_mobile/services/api_service.dart';
import 'package:swmm_mobile/services/storage_service.dart';

class SyncScreen extends StatefulWidget {
  const SyncScreen({super.key});

  @override
  State<SyncScreen> createState() => _SyncScreenState();
}

class _SyncScreenState extends State<SyncScreen> {
  String syncStatus = 'idle';
  String? lastSync;
  String networkMode = 'online';
  String deviceId = 'mobile-device-001';
  List<Map<String, dynamic>> pendingChanges = [];

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
      setState(() => pendingChanges = changes);
    } catch (e) {
      debugPrint(e.toString());
    }
  }

  Future<void> registerDevice() async {
    if (networkMode == 'offline') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Veuillez repasser en ligne pour enregistrer l\'appareil')),
      );
      return;
    }
    try {
      final result = await syncService.registerSession(deviceId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Session enregistrée : ${result['device_id']}')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Impossible d\'enregistrer la session')),
        );
      }
    }
  }

  Future<void> deletePendingItem(String localId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Supprimer la modification'),
        content: const Text('Voulez-vous vraiment supprimer cet élément de la file d\'attente locale ?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Annuler')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Supprimer')),
        ],
      ),
    );
    if (confirmed == true) {
      await storageService.removePendingChange(localId);
      await loadSettings();
    }
  }

  Future<void> syncDown() async {
    if (networkMode == 'offline') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vous êtes en mode Hors ligne')),
      );
      return;
    }
    try {
      setState(() => syncStatus = 'downloading');
      final delta = await syncService.getDelta(0);
      setState(() => lastSync = DateTime.now().toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Téléchargement réussi : ${delta['changes'].length} changements reçus')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Échec de la synchronisation descendante')),
        );
      }
    } finally {
      setState(() => syncStatus = 'idle');
    }
  }

  Future<void> syncUp() async {
    if (networkMode == 'offline') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Repassez en mode connecté pour synchroniser')),
      );
      return;
    }
    if (pendingChanges.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Aucun changement local en attente')),
      );
      return;
    }
    try {
      setState(() => syncStatus = 'uploading');
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

      final result = await syncService.pushChanges(deviceId, formattedChanges);
      await storageService.clearPendingChanges();
      setState(() => lastSync = DateTime.now().toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Envoi réussi !\nAcceptés : ${result['accepted']}\nRejetés : ${result['rejected']}')),
        );
      }
      await loadSettings();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Échec de l\'envoi des données locales')),
        );
      }
    } finally {
      setState(() => syncStatus = 'idle');
    }
  }

  Future<void> fullSync() async {
    await syncDown();
    await syncUp();
  }

  Color getTypeColor(String type) {
    switch (type) {
      case 'incident': return const Color(0xFFe74c3c);
      case 'inspection': return const Color(0xFF3498db);
      case 'regard': return const Color(0xFFf1c40f);
      case 'conduite': return const Color(0xFF1abc9c);
      default: return const Color(0xFF95a5a6);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synchronisation'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Statut réseau',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Mode : ${networkMode == 'online' ? 'Connecté' : 'Hors ligne'}',
                      style: const TextStyle(fontSize: 12),
                    ),
                    Text(
                      'ID : $deviceId',
                      style: const TextStyle(fontSize: 12),
                    ),
                    Text(
                      'Dernière sync : ${lastSync ?? 'Jamais'}',
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                    const SizedBox(height: 12),
                    ElevatedButton(
                      onPressed: registerDevice,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2ecc71),
                      ),
                      child: const Text('Enregistrer l\'appareil'),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Actions',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton(
                            onPressed: syncStatus == 'idle' ? syncDown : null,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFF3498db),
                            ),
                            child: const Text('⬇ Delta'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: (syncStatus == 'idle' && pendingChanges.isNotEmpty) ? syncUp : null,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFFe67e22),
                            ),
                            child: Text('⬆ Envoyer (${pendingChanges.length})'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: syncStatus == 'idle' ? fullSync : null,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF9b59b6),
                        ),
                        child: const Text('🔄 Synchronisation Complète'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (syncStatus != 'idle') ...[
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(width: 10),
                      Text(
                        syncStatus == 'downloading'
                            ? 'Téléchargement...'
                            : 'Envoi des modifications...',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'File d\'attente locale (${pendingChanges.length})',
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    if (pendingChanges.isEmpty)
                      const Text(
                        'Aucun changement en attente',
                        style: TextStyle(
                          fontStyle: FontStyle.italic,
                          color: Colors.grey,
                        ),
                      )
                    else
                      ...pendingChanges.map((change) => ListTile(
                            contentPadding: const EdgeInsets.symmetric(vertical: 4),
                            leading: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: getTypeColor(change['type'] as String),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                (change['type'] as String).toUpperCase(),
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 9,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                            title: Text(
                              change['type'] == 'incident'
                                  ? '${change['type_incident']} [${change['gravite']}]'
                                  : 'Équipement ID: ${change['object_id']}',
                              style: const TextStyle(fontSize: 12),
                            ),
                            trailing: IconButton(
                              icon: const Icon(Icons.delete, size: 20),
                              onPressed: () => deletePendingItem(change['localId'] as String),
                            ),
                          )),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 30),
          ],
        ),
      ),
    );
  }
}