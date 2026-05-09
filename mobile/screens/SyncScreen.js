import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { syncService } from '../services/api';

export default function SyncScreen() {
  const [syncStatus, setSyncStatus] = useState('idle');
  const [lastSync, setLastSync] = useState(null);
  const [deviceId, setDeviceId] = useState('mobile-device-001');
  const [pendingChanges, setPendingChanges] = useState([]);

  useEffect(() => {
    // Simuler quelques changements en attente pour la démo
    setPendingChanges([
      { id: 1, type: 'regard', action: 'update', description: 'Modification regard R001' },
      { id: 2, type: 'conduite', action: 'create', description: 'Nouvelle conduite C045' },
    ]);
  }, []);

  const registerDevice = async () => {
    try {
      const result = await syncService.registerSession(deviceId);
      Alert.alert('Succès', `Session enregistrée: ${result.device_id}`);
    } catch (error) {
      Alert.alert('Erreur', 'Impossible d\'enregistrer la session');
    }
  };

  const syncDown = async () => {
    try {
      setSyncStatus('downloading');
      const delta = await syncService.getDelta(0);
      setLastSync(new Date().toLocaleString());
      Alert.alert('Succès', `Synchronisation descendante terminée. ${delta.changes.length} changements reçus.`);
      setSyncStatus('idle');
    } catch (error) {
      setSyncStatus('idle');
      Alert.alert('Erreur', 'Échec de la synchronisation descendante');
    }
  };

  const syncUp = async () => {
    if (pendingChanges.length === 0) {
      Alert.alert('Info', 'Aucun changement en attente');
      return;
    }

    try {
      setSyncStatus('uploading');

      const changes = pendingChanges.map(change => ({
        type: change.action,
        layer: change.type,
        feature_id: change.id.toString(),
        changes: { description: change.description }
      }));

      const result = await syncService.pushChanges(changes);
      setLastSync(new Date().toLocaleString());
      Alert.alert('Succès',
        `Synchronisation montante terminée.\nAcceptés: ${result.accepted}\nRejetés: ${result.rejected}`
      );
      setPendingChanges([]);
      setSyncStatus('idle');
    } catch (error) {
      setSyncStatus('idle');
      Alert.alert('Erreur', 'Échec de la synchronisation montante');
    }
  };

  const fullSync = async () => {
    await syncDown();
    if (syncStatus === 'idle') {
      await syncUp();
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Synchronisation</Text>
        <Text style={styles.subtitle}>Synchroniser les données avec le serveur</Text>
      </View>

      <View style={styles.deviceCard}>
        <Text style={styles.cardTitle}>Appareil</Text>
        <Text style={styles.deviceId}>ID: {deviceId}</Text>
        <Text style={styles.lastSync}>
          Dernière sync: {lastSync || 'Jamais'}
        </Text>
        <TouchableOpacity style={styles.registerButton} onPress={registerDevice}>
          <Text style={styles.registerButtonText}>Enregistrer l'appareil</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.syncCard}>
        <Text style={styles.cardTitle}>Actions de synchronisation</Text>

        <TouchableOpacity
          style={[styles.syncButton, styles.downloadButton]}
          onPress={syncDown}
          disabled={syncStatus !== 'idle'}
        >
          <Text style={styles.downloadButtonText}>⬇ Télécharger</Text>
          <Text style={styles.buttonSubtitle}>Server → Mobile</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.syncButton,
            styles.uploadButton,
            pendingChanges.length === 0 && styles.disabledButton
          ]}
          onPress={syncUp}
          disabled={syncStatus !== 'idle' || pendingChanges.length === 0}
        >
          <Text style={styles.uploadButtonText}>⬆ Envoyer ({pendingChanges.length})</Text>
          <Text style={styles.buttonSubtitle}>Mobile → Server</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.syncButton, styles.fullSyncButton]}
          onPress={fullSync}
          disabled={syncStatus !== 'idle'}
        >
          <Text style={styles.fullSyncButtonText}>🔄 Sync Complète</Text>
          <Text style={styles.buttonSubtitle}>Bidirectionnelle</Text>
        </TouchableOpacity>
      </View>

      {syncStatus !== 'idle' && (
        <View style={styles.statusCard}>
          <ActivityIndicator size="small" color="#16213e" />
          <Text style={styles.statusText}>
            {syncStatus === 'downloading' ? 'Téléchargement...' :
             syncStatus === 'uploading' ? 'Envoi...' : 'Synchronisation...'}
          </Text>
        </View>
      )}

      <View style={styles.pendingCard}>
        <Text style={styles.cardTitle}>Changements en attente</Text>
        {pendingChanges.length === 0 ? (
          <Text style={styles.emptyText}>Aucun changement en attente</Text>
        ) : (
          pendingChanges.map((change, index) => (
            <View key={index} style={styles.pendingItem}>
              <Text style={styles.pendingAction}>{change.action.toUpperCase()}</Text>
              <Text style={styles.pendingDescription}>{change.description}</Text>
            </View>
          ))
        )}
      </View>

      <View style={styles.info}>
        <Text style={styles.infoTitle}>À propos de la synchronisation</Text>
        <Text style={styles.infoText}>
          • Télécharger : Récupère les dernières données du serveur
        </Text>
        <Text style={styles.infoText}>
          • Envoyer : Pousse vos modifications locales vers le serveur
        </Text>
        <Text style={styles.infoText}>
          • Sync complète : Télécharge puis envoie en une opération
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#16213e',
    padding: 20,
    alignItems: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#ddd',
    textAlign: 'center',
  },
  deviceCard: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#16213e',
    marginBottom: 12,
  },
  deviceId: {
    fontSize: 16,
    color: '#666',
    marginBottom: 4,
  },
  lastSync: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  registerButton: {
    backgroundColor: '#27ae60',
    padding: 12,
    borderRadius: 6,
    alignItems: 'center',
  },
  registerButtonText: {
    color: '#fff',
    fontWeight: 'bold',
  },
  syncCard: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  syncButton: {
    padding: 16,
    borderRadius: 8,
    marginBottom: 12,
    alignItems: 'center',
  },
  downloadButton: {
    backgroundColor: '#3498db',
  },
  downloadButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  uploadButton: {
    backgroundColor: '#e67e22',
  },
  uploadButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  fullSyncButton: {
    backgroundColor: '#9b59b6',
  },
  fullSyncButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  disabledButton: {
    backgroundColor: '#bdc3c7',
  },
  buttonSubtitle: {
    color: '#fff',
    fontSize: 12,
    opacity: 0.8,
  },
  statusCard: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusText: {
    marginLeft: 12,
    fontSize: 16,
    color: '#16213e',
  },
  pendingCard: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 8,
  },
  pendingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    backgroundColor: '#f8f9fa',
    borderRadius: 4,
    marginBottom: 8,
  },
  pendingAction: {
    backgroundColor: '#3498db',
    color: '#fff',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 'bold',
    marginRight: 12,
  },
  pendingDescription: {
    flex: 1,
    fontSize: 14,
    color: '#666',
  },
  emptyText: {
    textAlign: 'center',
    color: '#666',
    fontStyle: 'italic',
  },
  info: {
    padding: 16,
    backgroundColor: '#fff',
    margin: 16,
    borderRadius: 8,
  },
  infoTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
    color: '#16213e',
  },
  infoText: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
});