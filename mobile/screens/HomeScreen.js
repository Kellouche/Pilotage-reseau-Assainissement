/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Écran d'accueil principal de l'application mobile. Fournit l'état de connexion, 
 * un interrupteur de mode hors ligne, un badge des modifications locales en attente, 
 * et la navigation vers les modules cartographiques et de synchronisation.
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  Switch,
} from 'react-native';
import { healthService } from '../services/api';
import { storageService } from '../services/storage';

export default function HomeScreen({ navigation }) {
  const [networkMode, setNetworkMode] = useState('online');
  const [serverStatus, setServerStatus] = useState('checking');
  const [serverInfo, setServerInfo] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    loadSettings();
    const unsubscribe = navigation.addListener('focus', () => {
      loadSettings();
    });
    return unsubscribe;
  }, [navigation]);

  const loadSettings = async () => {
    try {
      const mode = await storageService.getNetworkMode();
      setNetworkMode(mode);
      
      const changes = await storageService.getPendingChanges();
      setPendingCount(changes.length);

      if (mode === 'online') {
        checkServerStatus();
      } else {
        setServerStatus('offline');
      }
    } catch (e) {
      console.error(e);
    }
  };

  const toggleNetworkMode = async (value) => {
    const newMode = value ? 'online' : 'offline';
    setNetworkMode(newMode);
    await storageService.setNetworkMode(newMode);
    if (newMode === 'online') {
      checkServerStatus();
    } else {
      setServerStatus('offline');
      setServerInfo(null);
    }
  };

  const checkServerStatus = async () => {
    try {
      setServerStatus('checking');
      const healthData = await healthService.checkHealth();
      setServerStatus('online');
      setServerInfo(healthData);
    } catch (error) {
      setServerStatus('offline');
      Alert.alert(
        'Erreur de connexion',
        'Impossible de contacter le serveur FastAPI. Vérifiez qu\'il est lancé.'
      );
    }
  };

  const getStatusColor = () => {
    if (networkMode === 'offline') return '#e67e22'; // Orange pour mode hors ligne
    switch (serverStatus) {
      case 'online': return '#27ae60';
      case 'offline': return '#e74c3c';
      case 'checking': return '#f39c12';
      default: return '#95a5a6';
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>SWMM Platform Mobile</Text>
        <Text style={styles.subtitle}>Outil terrain d'assainissement</Text>
      </View>

      {/* Switch Mode Réseau */}
      <View style={styles.networkSwitchCard}>
        <View style={styles.switchHeader}>
          <Text style={styles.switchTitle}>🔌 Mode Réseau Simulré</Text>
          <Switch
            value={networkMode === 'online'}
            onValueChange={toggleNetworkMode}
            trackColor={{ false: '#7f8c8d', true: '#2ecc71' }}
          />
        </View>
        <Text style={styles.switchDesc}>
          {networkMode === 'online'
            ? 'Mode connecté : Les données s\'envoient directement au serveur.'
            : 'Mode hors ligne : Toutes vos observations et incidents sont stockés localement.'}
        </Text>
      </View>

      {/* État du serveur */}
      <View style={styles.statusCard}>
        <Text style={styles.statusLabel}>État du système :</Text>
        <View style={[styles.statusIndicator, { backgroundColor: getStatusColor() }]} />
        <Text style={[styles.statusText, { color: getStatusColor() }]}>
          {networkMode === 'offline' ? 'Application Hors ligne' :
           serverStatus === 'online' ? 'Serveur en ligne ✓' :
           serverStatus === 'offline' ? 'Serveur injoignable ✗' : 'Vérification...'}
        </Text>
        
        {serverInfo && networkMode === 'online' && (
          <View style={styles.serverInfo}>
            <Text style={styles.infoText}>Base DB : {serverInfo.database}</Text>
            <Text style={styles.infoText}>Cache Graphe : {serverInfo.graph_cache}</Text>
          </View>
        )}
        
        {networkMode === 'online' && (
          <TouchableOpacity style={styles.refreshButton} onPress={checkServerStatus}>
            <Text style={styles.refreshButtonText}>Actualiser</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Menu Principal */}
      <View style={styles.menu}>
        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => navigation.navigate('Map')}
        >
          <View style={styles.menuItemHeader}>
            <Text style={styles.menuItemTitle}>🗺️ Carte & Collecte</Text>
            {pendingCount > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{pendingCount}</Text>
              </View>
            )}
          </View>
          <Text style={styles.menuItemDescription}>
            Fiches terrain, photos, GPS et signalement d'incidents
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => navigation.navigate('Sync')}
        >
          <View style={styles.menuItemHeader}>
            <Text style={styles.menuItemTitle}>🔄 Synchronisation</Text>
            {pendingCount > 0 && (
              <View style={styles.badgeOrange}>
                <Text style={styles.badgeText}>{pendingCount}</Text>
              </View>
            )}
          </View>
          <Text style={styles.menuItemDescription}>
            Synchroniser les données locales vers le bureau d'études
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>Version mobile 1.0.0 -- Dr A. Kellouche</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f6fa' },
  header: { backgroundColor: '#16213e', padding: 24, alignItems: 'center', borderBottomLeftRadius: 16, borderBottomRightRadius: 16 },
  title: { fontSize: 22, fontWeight: 'bold', color: '#fff' },
  subtitle: { fontSize: 13, color: '#bdc3c7', marginTop: 4 },
  networkSwitchCard: { backgroundColor: '#fff', margin: 16, padding: 16, borderRadius: 12, elevation: 2 },
  switchHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  switchTitle: { fontSize: 15, fontWeight: 'bold', color: '#2c3e50' },
  switchDesc: { fontSize: 12, color: '#7f8c8d', lineHeight: 18 },
  statusCard: { backgroundColor: '#fff', marginHorizontal: 16, marginBottom: 16, padding: 16, borderRadius: 12, elevation: 2, alignItems: 'center' },
  statusLabel: { fontSize: 14, fontWeight: 'bold', color: '#7f8c8d', marginBottom: 8 },
  statusIndicator: { width: 14, height: 14, borderRadius: 7, marginBottom: 6 },
  statusText: { fontSize: 15, fontWeight: 'bold', marginBottom: 8 },
  serverInfo: { width: '100%', borderTopWidth: 1, borderTopColor: '#f1f2f6', paddingTop: 8, marginTop: 8 },
  infoText: { fontSize: 12, color: '#57606f', marginBottom: 2 },
  refreshButton: { backgroundColor: '#16213e', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 6, marginTop: 8 },
  refreshButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 12 },
  menu: { padding: 16 },
  menuItem: { backgroundColor: '#fff', padding: 16, borderRadius: 12, marginBottom: 12, elevation: 2 },
  menuItemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  menuItemTitle: { fontSize: 16, fontWeight: 'bold', color: '#16213e' },
  menuItemDescription: { fontSize: 12, color: '#7f8c8d', lineHeight: 16 },
  badge: { backgroundColor: '#2ecc71', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  badgeOrange: { backgroundColor: '#e67e22', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: 'bold' },
  footer: { alignItems: 'center', marginTop: 24, marginBottom: 30 },
  footerText: { fontSize: 11, color: '#a4b0be', fontStyle: 'italic' },
});
