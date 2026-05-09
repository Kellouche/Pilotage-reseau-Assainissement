import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
} from 'react-native';
import { healthService } from '../services/api';

export default function HomeScreen({ navigation }) {
  const [serverStatus, setServerStatus] = useState('checking');
  const [serverInfo, setServerInfo] = useState(null);

  useEffect(() => {
    checkServerStatus();
  }, []);

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
        'Impossible de contacter le serveur. Vérifiez que le serveur FastAPI est démarré sur le port 5001.'
      );
    }
  };

  const getStatusColor = () => {
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
        <Text style={styles.subtitle}>Application mobile pour la gestion du réseau d'assainissement</Text>
      </View>

      <View style={styles.statusCard}>
        <Text style={styles.statusLabel}>État du serveur:</Text>
        <View style={[styles.statusIndicator, { backgroundColor: getStatusColor() }]} />
        <Text style={[styles.statusText, { color: getStatusColor() }]}>
          {serverStatus === 'online' ? 'Serveur en ligne' :
           serverStatus === 'offline' ? 'Serveur hors ligne' : 'Vérification...'}
        </Text>
        {serverInfo && (
          <View style={styles.serverInfo}>
            <Text style={styles.infoText}>Base de données: {serverInfo.database}</Text>
            <Text style={styles.infoText}>Cache graphe: {serverInfo.graph_cache}</Text>
          </View>
        )}
        <TouchableOpacity style={styles.refreshButton} onPress={checkServerStatus}>
          <Text style={styles.refreshButtonText}>Actualiser</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.menu}>
        <TouchableOpacity
          style={[styles.menuItem, serverStatus !== 'online' && styles.menuItemDisabled]}
          onPress={() => navigation.navigate('Map')}
          disabled={serverStatus !== 'online'}
        >
          <Text style={styles.menuItemTitle}>🗺 Carte du Réseau</Text>
          <Text style={styles.menuItemDescription}>
            Visualiser les conduites, regards et bassins versants
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.menuItem, serverStatus !== 'online' && styles.menuItemDisabled]}
          onPress={() => navigation.navigate('Sync')}
          disabled={serverStatus !== 'online'}
        >
          <Text style={styles.menuItemTitle}>🔄 Synchronisation</Text>
          <Text style={styles.menuItemDescription}>
            Synchroniser les données avec le serveur
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.info}>
        <Text style={styles.infoTitle}>Fonctionnalités</Text>
        <Text style={styles.infoText}>• Visualisation du réseau d'assainissement</Text>
        <Text style={styles.infoText}>• Détection automatique des bassins versants</Text>
        <Text style={styles.infoText}>• Synchronisation hors ligne</Text>
        <Text style={styles.infoText}>• Collecte de données sur le terrain</Text>
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
  statusCard: {
    backgroundColor: '#fff',
    margin: 16,
    padding: 16,
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
    alignItems: 'center',
  },
  statusLabel: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  statusIndicator: {
    width: 20,
    height: 20,
    borderRadius: 10,
    marginBottom: 8,
  },
  statusText: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  serverInfo: {
    width: '100%',
    marginBottom: 12,
  },
  infoText: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  refreshButton: {
    backgroundColor: '#3498db',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 6,
  },
  refreshButtonText: {
    color: '#fff',
    fontWeight: 'bold',
  },
  menu: {
    padding: 16,
  },
  menuItem: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 8,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  menuItemDisabled: {
    backgroundColor: '#f8f8f8',
    opacity: 0.6,
  },
  menuItemTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#16213e',
    marginBottom: 4,
  },
  menuItemDescription: {
    fontSize: 14,
    color: '#666',
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
});
