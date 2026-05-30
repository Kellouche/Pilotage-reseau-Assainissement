import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

class StorageService {
  static const _networkModeKey = 'NETWORK_MODE';
  static const _pendingChangesKey = 'PENDING_CHANGES';

  Future<String> getNetworkMode() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_networkModeKey) ?? 'online';
  }

  Future<void> setNetworkMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_networkModeKey, mode);
  }

  Future<List<Map<String, dynamic>>> getPendingChanges() async {
    final prefs = await SharedPreferences.getInstance();
    final changesJson = prefs.getString(_pendingChangesKey);
    if (changesJson == null) return [];
    return List<Map<String, dynamic>>.from(
      json.decode(changesJson).map((e) => Map<String, dynamic>.from(e)),
    );
  }

  Future<Map<String, dynamic>> addPendingChange(Map<String, dynamic> change) async {
    final changes = await getPendingChanges();
    final newChange = {
      'localId': DateTime.now().millisecondsSinceEpoch.toString() + 
          (DateTime.now().microsecond % 1000).toString(),
      'timestamp': DateTime.now().toIso8601String(),
      ...change,
    };
    changes.add(newChange);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingChangesKey, json.encode(changes));
    return newChange;
  }

  Future<void> removePendingChange(String localId) async {
    final changes = await getPendingChanges();
    changes.removeWhere((c) => c['localId'] != localId);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingChangesKey, json.encode(changes));
  }

  Future<void> clearPendingChanges() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingChangesKey, json.encode([]));
  }
}

final storageService = StorageService();