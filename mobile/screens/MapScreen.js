import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
} from 'react-native';
import MapView, { Polyline, Marker } from 'react-native-maps';
import { networkService, clusterService } from '../services/api';

export default function MapScreen() {
  const [layers, setLayers] = useState(null);
  const [clusters, setClusters] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showClusters, setShowClusters] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingConduit, setEditingConduit] = useState(null);
  const [editForm, setEditForm] = useState({
    longueur: '',
    diametre: '',
    materiau: '',
    f_nom: '',
  });

  useEffect(() => {
    loadNetworkData();
  }, []);

  const loadNetworkData = async () => {
    try {
      setLoading(true);
      const layersData = await networkService.getLayers();
      setLayers(layersData);
    } catch (error) {
      Alert.alert('Erreur', 'Impossible de charger les données du réseau');
    } finally {
      setLoading(false);
    }
  };

  const detectClusters = async () => {
    try {
      setLoading(true);
      const clusterData = await clusterService.detectClusters();
      setClusters(clusterData.resultats);
      setShowClusters(true);
      Alert.alert('Succès', `${clusterData.clusters_crees} bassins détectés`);
    } catch (error) {
      Alert.alert('Erreur', 'Impossible de détecter les bassins versants');
    } finally {
      setLoading(false);
    }
  };

  const openEditConduit = (conduit) => {
    Alert.alert('Edit Conduit', `Opening edit for conduit ${conduit.id || conduit.fid}`);
    setEditingConduit(conduit);
    setEditForm({
      longueur: conduit.longueur?.toString() || '',
      diametre: conduit.diametre?.toString() || '',
      materiau: conduit.materiau || '',
      f_nom: conduit.f_nom || '',
    });
    setEditModalVisible(true);
  };

  const saveConduitEdit = async () => {
    try {
      const updateData = {
        longueur: parseFloat(editForm.longueur) || null,
        diametre: parseFloat(editForm.diametre) || null,
        materiau: editForm.materiau || null,
        f_nom: editForm.f_nom || null,
      };

      await networkService.updateConduite(editingConduit.id, updateData);
      Alert.alert('Succès', 'Conduite mise à jour');
      setEditModalVisible(false);
      // Recharger les données
      loadNetworkData();
    } catch (error) {
      Alert.alert('Erreur', 'Impossible de mettre à jour la conduite');
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#16213e" />
        <Text style={styles.loadingText}>Chargement des données...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.controls}>
        <TouchableOpacity
          style={[styles.button, styles.primaryButton]}
          onPress={loadNetworkData}
        >
          <Text style={styles.primaryButtonText}>🔄 Actualiser</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.button, styles.secondaryButton]}
          onPress={detectClusters}
        >
          <Text style={styles.secondaryButtonText}>
            🏔 Détecter Bassins
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.button, styles.secondaryButton]}
          onPress={() => openEditConduit({
            id: 1,
            longueur: 100,
            diametre: 200,
            materiau: 'PVC',
            f_nom: 'Test Conduite'
          })}
        >
          <Text style={styles.secondaryButtonText}>
            ✏️ Test Edit Conduite
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.legend}>
        <Text style={styles.legendTitle}>Légende:</Text>
        <View style={styles.legendItem}>
          <View style={[styles.legendColor, { backgroundColor: '#3498db' }]} />
          <Text style={styles.legendText}>Conduites</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendColor, { backgroundColor: '#f1c40f' }]} />
          <Text style={styles.legendText}>Regards</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendColor, { backgroundColor: '#e67e22' }]} />
          <Text style={styles.legendText}>Stations</Text>
        </View>
        {showClusters && (
          <View style={styles.legendItem}>
            <View style={[styles.legendColor, { backgroundColor: '#27ae60' }]} />
            <Text style={styles.legendText}>Bassins</Text>
          </View>
        )}
      </View>

      <MapView
        style={styles.map}
        initialRegion={{
          latitude: 36.15,
          longitude: 1.33,
          latitudeDelta: 0.1,
          longitudeDelta: 0.1,
        }}
      >
        {/* Conduites */}
        {layers?.couches?.conduites?.features?.map((feature, index) => (
          <Polyline
            key={`conduite-${index}`}
            coordinates={feature.geometry.coordinates.map(coord => ({
              latitude: coord[1],
              longitude: coord[0],
            }))}
            strokeColor="#3498db"
            strokeWidth={8}
            onPress={() => openEditConduit(feature.properties)}
          />
        ))}

        {/* Regards */}
        {layers?.couches?.regards?.features?.map((feature, index) => (
          <Marker
            key={`regard-${index}`}
            coordinate={{
              latitude: feature.geometry.coordinates[1],
              longitude: feature.geometry.coordinates[0],
            }}
            title={`Regard ${feature.properties.code || feature.properties.id}`}
            description={`Diamètre: ${feature.properties.diametre}mm`}
          />
        ))}

        {/* Stations */}
        {layers?.couches?.stations?.features?.map((feature, index) => (
          <Marker
            key={`station-${index}`}
            coordinate={{
              latitude: feature.geometry.coordinates[1],
              longitude: feature.geometry.coordinates[0],
            }}
            pinColor="#e67e22"
            title={`Station ${feature.properties.nom || feature.properties.id}`}
          />
        ))}

        {/* STEP */}
        {layers?.couches?.step?.features?.map((feature, index) => (
          <Marker
            key={`step-${index}`}
            coordinate={{
              latitude: feature.geometry.coordinates[1],
              longitude: feature.geometry.coordinates[0],
            }}
            pinColor="#27ae60"
            title={`STEP ${feature.properties.nom || feature.properties.id}`}
          />
        ))}

        {/* Ouvrages */}
        {layers?.couches?.ouvrages?.features?.map((feature, index) => (
          <Marker
            key={`ouvrage-${index}`}
            coordinate={{
              latitude: feature.geometry.coordinates[1],
              longitude: feature.geometry.coordinates[0],
            }}
            pinColor="#9b59b6"
            title={`Ouvrage ${feature.properties.nom || feature.properties.id}`}
          />
        ))}
      </MapView>

      {/* Modal d'édition des conduites */}
      <Modal
        visible={editModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setEditModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Modifier Conduite</Text>

            <Text style={styles.inputLabel}>Longueur (m):</Text>
            <TextInput
              style={styles.textInput}
              value={editForm.longueur}
              onChangeText={(text) => setEditForm({...editForm, longueur: text})}
              keyboardType="numeric"
              placeholder="Longueur"
            />

            <Text style={styles.inputLabel}>Diamètre (mm):</Text>
            <TextInput
              style={styles.textInput}
              value={editForm.diametre}
              onChangeText={(text) => setEditForm({...editForm, diametre: text})}
              keyboardType="numeric"
              placeholder="Diamètre"
            />

            <Text style={styles.inputLabel}>Matériau:</Text>
            <TextInput
              style={styles.textInput}
              value={editForm.materiau}
              onChangeText={(text) => setEditForm({...editForm, materiau: text})}
              placeholder="Matériau"
            />

            <Text style={styles.inputLabel}>Nom:</Text>
            <TextInput
              style={styles.textInput}
              value={editForm.f_nom}
              onChangeText={(text) => setEditForm({...editForm, f_nom: text})}
              placeholder="Nom"
            />

            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={[styles.button, styles.cancelButton]}
                onPress={() => setEditModalVisible(false)}
              >
                <Text style={styles.cancelButtonText}>Annuler</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.button, styles.primaryButton]}
                onPress={saveConduitEdit}
              >
                <Text style={styles.primaryButtonText}>Enregistrer</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  loadingText: {
    marginTop: 16,
    fontSize: 16,
    color: '#666',
  },
  controls: {
    flexDirection: 'row',
    padding: 16,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  button: {
    flex: 1,
    padding: 12,
    borderRadius: 6,
    marginHorizontal: 4,
    alignItems: 'center',
  },
  primaryButton: {
    backgroundColor: '#16213e',
  },
  primaryButtonText: {
    color: '#fff',
    fontWeight: 'bold',
  },
  secondaryButton: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#16213e',
  },
  secondaryButtonText: {
    color: '#16213e',
    fontWeight: 'bold',
  },
  legend: {
    backgroundColor: '#fff',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  legendTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 8,
    color: '#16213e',
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  legendColor: {
    width: 16,
    height: 16,
    borderRadius: 2,
    marginRight: 8,
  },
  legendText: {
    fontSize: 14,
    color: '#666',
  },
  map: {
    flex: 1,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    backgroundColor: '#fff',
    padding: 20,
    borderRadius: 10,
    width: '90%',
    maxHeight: '80%',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
    color: '#16213e',
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    marginBottom: 5,
    color: '#333',
  },
  textInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 5,
    padding: 10,
    marginBottom: 15,
    fontSize: 16,
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 20,
  },
  cancelButton: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#16213e',
    flex: 1,
    marginRight: 10,
  },
  cancelButtonText: {
    color: '#16213e',
  },
});