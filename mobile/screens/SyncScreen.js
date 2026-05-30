/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Écran de gestion de la synchronisation bidirectionnelle. Permet de visualiser, 
 * filtrer et supprimer les modifications locales en attente, d'effectuer des 
 * envois/téléchargements manuels ou des synchronisations complètes.
 */

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
import { storageService } from '../services/storage';

export default function SyncScreen() {
  const [syncStatus, setSyncStatus] = useState('idle');
  const [lastSync, setLastSync] = useState(null);
  const [networkMode, setNetworkMode] = useState('online');
  const [deviceId, setDeviceId] = useState('mobile-device-001');
  const [pendingChanges, setPendingChanges] = useState([]);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const mode = await storageService.getNetworkMode();
      setNetworkMode(mode);
      const changes = await storageService.getPendingChanges();
      setPendingChanges(changes);
    } catch (e) {
      console.error(e);
    }
  };

  const registerDevice = async () => {
    if (networkMode === 'offline') {
      Alert.alert('Info', 'Veuillez repasser en ligne pour enregistrer l\'appareil');
      return;
    }
    try {
      const result = await syncService.registerSession(deviceId);
      Alert.alert('Succès', `Session enregistrée : ${result.device_id}`);
    } catch (error) {
      Alert.alert('Erreur', 'Impossible d\'enregistrer la session');
    }
  };

  const deletePendingItem = async (localId) => {
    Alert.alert(
      'Supprimer la modification',
      'Voulez-vous vraiment supprimer cet élément de la file d\'attente locale ?',
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: async () => {
            await storageService.removePendingChange(localId);
            await loadSettings();
          }
        }
      ]
    );
  };

  const syncDown = async () => {
    if (networkMode === 'offline') {
      Alert.alert('Erreur', 'Vous êtes en mode Hors ligne.');
      return;
    }
    try {
      setSyncStatus('downloading');
      const delta = await syncService.getDelta(0);
      setLastSync(new Date().toLocaleString());
      Alert.alert('Succès', `Téléchargement réussi : ${delta.changes.length} changements reçus.`);
      setSyncStatus('idle');
    } catch (error) {
      setSyncStatus('idle');
      Alert.alert('Erreur', 'Échec de la synchronisation descendante');
    }
  };

  const syncUp = async () => {
    if (networkMode === 'offline') {
      Alert.alert('Erreur', 'Repassez en mode connecté pour synchroniser.');
      return;
    }
    if (pendingChanges.length === 0) {
      Alert.alert('Info', 'Aucun changement local en attente.');
      return;
    }

    try {
      setSyncStatus('uploading');
      
      // Formater pour l'API sync/push
      const formattedChanges = pendingChanges.map(change => ({
        type: change.type === 'incident' ? 'create' : 'update',
        layer: change.type === 'incident' ? 'incidents' : change.type === 'inspection' ? 'inspections' : change.type + 's',
        feature_id: change.object_id || '0',
        changes: change
      }));

      const result = await syncService.pushChanges(deviceId, formattedChanges);
      await storageService.clearPendingChanges();
      setLastSync(new Date().toLocaleString());
      Alert.alert('Succès', `Envoi réussi !\nAcceptés : ${result.accepted}\nRejetés : ${result.rejected}`);
      await loadSettings();
      setSyncStatus('idle');
    } catch (error) {
      setSyncStatus('idle');
      Alert.alert('Erreur', 'Échec de l\'envoi des données locales.');
    }
  };

  const fullSync = async () => {
    await syncDown();
    await syncUp();
  };

  const renderBadge = (type) => {
    const colors = { incident: '#e74c3c', inspection: '#3498db', regard: '#f1c40f', conduite: '#1abc9c' };
    return (
      <View style={[styles.typeBadge, { backgroundColor: colors[type] || '#95a5a6' }]}>
        <Text style={styles.typeBadgeText}>{type.toUpperCase()}</Text>
      </View>
    );
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Synchronisation</Text>
        <Text style={styles.subtitle}>Statut réseau : {networkMode === 'online' ? 'Connecté' : 'Hors ligne'}</Text>
      </View>

      <View style={styles.deviceCard}>
        <Text style={styles.cardTitle}>Appareil</Text>
        <Text style={styles.deviceId}>ID : {deviceId}</Text>
        <Text style={styles.lastSync}>Dernière sync : {lastSync || 'Jamais'}</Text>
        <TouchableOpacity style={styles.registerButton} onPress={registerDevice}>
          <Text style={styles.registerButtonText}>Enregistrer l'appareil</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.syncCard}>
        <Text style={styles.cardTitle}>Actions</Text>
        <View style={styles.btnRow}>
          <TouchableOpacity style={[styles.syncButton, styles.downloadButton]} onPress={syncDown} disabled={syncStatus !== 'idle'}>
            <Text style={styles.btnText}>⬇ Delta</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.syncButton, styles.uploadButton]} onPress={syncUp} disabled={syncStatus !== 'idle' || pendingChanges.length === 0}>
            <Text style={styles.btnText}>⬆ Envoyer ({pendingChanges.length})</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity style={[styles.syncButton, styles.fullSyncButton]} onPress={fullSync} disabled={syncStatus !== 'idle'}>
          <Text style={styles.btnText}>🔄 Synchronisation Complète</Text>
        </TouchableOpacity>
      </View>

      {syncStatus !== 'idle' && (
        <View style={styles.statusCard}>
          <ActivityIndicator size="small" color="#16213e" />
          <Text style={styles.statusText}>
            {syncStatus === 'downloading' ? 'Téléchargement...' : 'Envoi des modifications...'}
          </Text>
        </View>
      )}

      {/* File d'attente locale */}
      <View style={styles.pendingCard}>
        <Text style={styles.cardTitle}>File d'attente locale ({pendingChanges.length})</Text>
        {pendingChanges.length === 0 ? (
          <Text style={styles.emptyText}>Aucun changement en attente</Text>
        ) : (
          pendingChanges.map((change, index) => (
            <View key={index} style={styles.pendingItem}>
              <View style={styles.pendingDetails}>
                {renderBadge(change.type)}
                <Text style={styles.pendingDesc}>
                  {change.type === 'incident' ? `${change.type_incident} [${change.gravite}]` : `Équipement ID: ${change.object_id}`}
                </Text>
              </View>
              <TouchableOpacity style={styles.deleteBtn} onPress={() => deletePendingItem(change.localId)}>
                <Text style={styles.deleteBtnText}>🗑️</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f6fa' },
  header: { backgroundColor: '#16213e', padding: 20, alignItems: 'center' },
  title: { fontSize: 20, fontWeight: 'bold', color: '#fff' },
  subtitle: { fontSize: 13, color: '#ddd', marginTop: 4 },
  deviceCard: { backgroundColor: '#fff', margin: 12, padding: 14, borderRadius: 10, elevation: 1 },
  cardTitle: { fontSize: 15, fontWeight: 'bold', color: '#16213e', marginBottom: 8 },
  deviceId: { fontSize: 13, color: '#555', marginBottom: 2 },
  lastSync: { fontSize: 12, color: '#888', marginBottom: 10 },
  registerButton: { backgroundColor: '#2ecc71', padding: 10, borderRadius: 6, alignItems: 'center' },
  registerButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 13 },
  syncCard: { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 12, padding: 14, borderRadius: 10, elevation: 1 },
  btnRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  syncButton: { flex: 1, padding: 12, borderRadius: 6, alignItems: 'center', marginHorizontal: 4 },
  downloadButton: { backgroundColor: '#3498db' },
  uploadButton: { backgroundColor: '#e67e22' },
  fullSyncButton: { backgroundColor: '#9b59b6', marginTop: 4 },
  btnText: { color: '#fff', fontWeight: 'bold', fontSize: 13 },
  statusCard: { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 12, padding: 12, borderRadius: 8, flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  statusText: { marginLeft: 10, fontSize: 13, color: '#16213e', fontWeight: 'bold' },
  pendingCard: { backgroundColor: '#fff', marginHorizontal: 12, marginBottom: 30, padding: 14, borderRadius: 10, elevation: 1 },
  pendingItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 10, backgroundColor: '#f8f9fa', borderRadius: 6, marginBottom: 8 },
  pendingDetails: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  typeBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginRight: 8 },
  typeBadgeText: { color: '#fff', fontSize: 9, fontWeight: 'bold' },
  pendingDesc: { fontSize: 12, color: '#555', flex: 1 },
  deleteBtn: { padding: 4 },
  deleteBtnText: { fontSize: 14 },
  emptyText: { textAlign: 'center', color: '#888', fontStyle: 'italic', fontSize: 13, paddingVertical: 10 }
});