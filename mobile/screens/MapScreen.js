/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Écran cartographique principal (SIG mobile). Affiche les conduites, regards,
 * stations et ouvrages. Intègre la géolocalisation, le calcul de proximité,
 * les fiches d'inspection, la déclaration d'incidents et le simulateur QR.
 */

import React, { useEffect, useState, useRef } from 'react';
import { View, StyleSheet, TouchableOpacity, Text, Alert, Modal } from 'react-native';
import MapView, { Polyline, Marker } from 'react-native-maps';
import * as Location from 'expo-location';

import { networkService } from '../services/api';
import { storageService } from '../services/storage';
import FicheTerrain from '../components/FicheTerrain';
import IncidentForm from '../components/IncidentForm';
import ScannerSim from '../components/ScannerSim';
import ProximiteList from '../components/ProximiteList';

export default function MapScreen() {
  const mapRef = useRef(null);
  const [layers, setLayers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [networkMode, setNetworkMode] = useState('online');

  // GPS & États Position
  const [userLocation, setUserLocation] = useState(null);

  // Modals & États Fiches
  const [activeObject, setActiveObject] = useState(null);
  const [activeType, setActiveType] = useState('regard');
  const [showProximite, setShowProximite] = useState(false);
  const [showScanner, setShowScanner] = useState(false);
  
  // Incidents
  const [declaringIncident, setDeclaringIncident] = useState(false);
  const [tempCoordinate, setTempCoordinate] = useState(null);
  const [showIncidentForm, setShowIncidentForm] = useState(false);
  const [localIncidents, setLocalIncidents] = useState([]);

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const mode = await storageService.getNetworkMode();
      setNetworkMode(mode);
      const data = await networkService.getLayers();
      setLayers(data);
      requestGPSLocation();
    } catch (e) {
      Alert.alert('Erreur', 'Impossible de charger la carte');
    } finally {
      setLoading(false);
    }
  };

  const requestGPSLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      const loc = await Location.getCurrentPositionAsync({});
      setUserLocation(loc.coords);
    } catch (e) {
      console.warn('GPS non disponible');
    }
  };

  const centerOnUser = () => {
    if (!userLocation || !mapRef.current) {
      Alert.alert('GPS', 'Position GPS non encore détectée.');
      return;
    }
    mapRef.current.animateToRegion({
      latitude: userLocation.latitude,
      longitude: userLocation.longitude,
      latitudeDelta: 0.005,
      longitudeDelta: 0.005,
    }, 1000);
  };

  const handleMapPress = (e) => {
    if (declaringIncident) {
      setTempCoordinate(e.nativeEvent.coordinate);
      setShowIncidentForm(true);
      setDeclaringIncident(false);
    }
  };

  const saveInspection = async (inspectionData) => {
    try {
      if (networkMode === 'online') {
        // Envoi direct via API (si connectée)
        try {
          const api = require('../services/api').default;
          await api.post('/api/v1/terrain/inspections', inspectionData);
        } catch {
          await storageService.addPendingChange({ type: 'inspection', ...inspectionData });
        }
      } else {
        await storageService.addPendingChange({ type: 'inspection', ...inspectionData });
      }
      setActiveObject(null);
    } catch (e) {
      Alert.alert('Erreur', 'Impossible d\'enregistrer l\'inspection');
    }
  };

  const saveIncident = async (incidentData) => {
    try {
      if (networkMode === 'online') {
        try {
          const api = require('../services/api').default;
          const res = await api.post('/api/v1/terrain/incidents', incidentData);
          setLocalIncidents([...localIncidents, res.data]);
        } catch {
          const saved = await storageService.addPendingChange({ type: 'incident', ...incidentData });
          setLocalIncidents([...localIncidents, saved]);
        }
      } else {
        const saved = await storageService.addPendingChange({ type: 'incident', ...incidentData });
        setLocalIncidents([...localIncidents, saved]);
      }
      setShowIncidentForm(false);
      setTempCoordinate(null);
    } catch (e) {
      Alert.alert('Erreur', 'Impossible d\'enregistrer l\'incident');
    }
  };

  const getScannerTargets = () => {
    const list = [];
    if (layers?.couches?.regards?.features) {
      layers.couches.regards.features.slice(0, 5).forEach(f => {
        list.push({ type: 'regard', object: f.properties });
      });
    }
    return list;
  };

  return (
    <View style={styles.container}>
      <MapView
        ref={mapRef}
        style={styles.map}
        initialRegion={{
          latitude: 36.15,
          longitude: 1.33,
          latitudeDelta: 0.05,
          longitudeDelta: 0.05,
        }}
        onPress={handleMapPress}
      >
        {/* Regards */}
        {layers?.couches?.regards?.features?.map((f, i) => (
          <Marker
            key={`regard-${i}`}
            coordinate={{ latitude: f.geometry.coordinates[1], longitude: f.geometry.coordinates[0] }}
            pinColor="#f1c40f"
            onPress={() => { setActiveType('regard'); setActiveObject(f.properties); }}
          />
        ))}

        {/* Conduites */}
        {layers?.couches?.conduites?.features?.map((f, i) => (
          <Polyline
            key={`conduite-${i}`}
            coordinates={f.geometry.coordinates.map(c => ({ latitude: c[1], longitude: c[0] }))}
            strokeColor="#3498db"
            strokeWidth={5}
            tappable
            onPress={() => { setActiveType('conduite'); setActiveObject(f.properties); }}
          />
        ))}

        {/* Incidents locaux signalés */}
        {localIncidents.map((inc, i) => (
          <Marker
            key={`incident-${i}`}
            coordinate={{ latitude: inc.latitude, longitude: inc.longitude }}
            pinColor="#e74c3c"
            title={inc.type_incident}
            description={inc.description}
          />
        ))}
      </MapView>

      {/* Barre de boutons flottants */}
      <View style={styles.floatingControls}>
        <TouchableOpacity style={styles.floatBtn} onPress={centerOnUser}>
          <Text style={styles.floatBtnText}>📍 GPS</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.floatBtn} onPress={() => setShowProximite(true)}>
          <Text style={styles.floatBtnText}>🔍 Proches</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.floatBtn} onPress={() => setShowScanner(true)}>
          <Text style={styles.floatBtnText}>📷 QR Scan</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.floatBtn, declaringIncident && styles.floatBtnActive]}
          onPress={() => setDeclaringIncident(!declaringIncident)}
        >
          <Text style={styles.floatBtnText}>🚨 Incident</Text>
        </TouchableOpacity>
      </View>

      {/* Modal Fiche Terrain */}
      <Modal visible={activeObject !== null} animationType="slide">
        {activeObject && (
          <FicheTerrain
            object={activeObject}
            type={activeType}
            onClose={() => setActiveObject(null)}
            onSave={saveInspection}
          />
        )}
      </Modal>

      {/* Modal Déclarer Incident */}
      <Modal visible={showIncidentForm} animationType="slide">
        {tempCoordinate && (
          <IncidentForm
            coordinate={tempCoordinate}
            onClose={() => { setShowIncidentForm(false); setTempCoordinate(null); }}
            onSave={saveIncident}
          />
        )}
      </Modal>

      {/* Modal Proximité */}
      <Modal visible={showProximite} animationType="slide">
        <ProximiteList
          location={userLocation || { latitude: 36.15, longitude: 1.33 }}
          networkData={layers}
          onClose={() => setShowProximite(false)}
          onSelect={(obj, type, coords) => {
            setShowProximite(false);
            setActiveType(type);
            setActiveObject(obj);
            if (mapRef.current) {
              mapRef.current.animateToRegion({ ...coords, latitudeDelta: 0.002, longitudeDelta: 0.002 }, 1000);
            }
          }}
        />
      </Modal>

      {/* Modal QR Scanner */}
      <Modal visible={showScanner} animationType="slide">
        <ScannerSim
          targets={getScannerTargets()}
          onClose={() => setShowScanner(false)}
          onScanSuccess={(obj, type) => {
            setShowScanner(false);
            setActiveType(type);
            setActiveObject(obj);
          }}
        />
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  floatingControls: { position: 'absolute', bottom: 20, left: 10, right: 10, flexDirection: 'row', justifyContent: 'space-around', backgroundColor: 'transparent' },
  floatBtn: { backgroundColor: '#16213e', paddingVertical: 10, paddingHorizontal: 14, borderRadius: 20, elevation: 3, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84 },
  floatBtnActive: { backgroundColor: '#e74c3c' },
  floatBtnText: { color: '#fff', fontSize: 12, fontWeight: 'bold' }
});