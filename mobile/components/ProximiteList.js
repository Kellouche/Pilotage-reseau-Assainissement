/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Composant de panneau mobile listant les équipements du réseau d'assainissement 
 * situés à proximité de la position GPS réelle ou simulée de l'utilisateur.
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
} from 'react-native';

// Formule de Haversine pour calculer la distance entre deux coordonnées GPS
function calculateDistance(lat1, lon1, lat2, lon2) {
  if (!lat1 || !lon1 || !lat2 || !lon2) return 999999;
  const R = 6371e3; // Rayon de la Terre en mètres
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const deltaPhi = ((lat2 - lat1) * Math.PI) / 180;
  const deltaLambda = ((lon2 - lon1) * Math.PI) / 180;

  const a =
    Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c; // Distance en mètres
}

export default function ProximiteList({ location, networkData, onSelect, onClose }) {
  const { latitude, longitude } = location;

  const getNearbyObjects = () => {
    const list = [];

    // Parcourir les regards
    if (networkData?.couches?.regards?.features) {
      networkData.couches.regards.features.forEach((feat) => {
        const [lon, lat] = feat.geometry.coordinates;
        const dist = calculateDistance(latitude, longitude, lat, lon);
        if (dist <= 500) { // Cibles à moins de 500 mètres
          list.push({
            type: 'regard',
            distance: dist,
            object: feat.properties,
            coords: { latitude: lat, longitude: lon }
          });
        }
      });
    }

    // Parcourir les stations
    if (networkData?.couches?.stations?.features) {
      networkData.couches.stations.features.forEach((feat) => {
        const [lon, lat] = feat.geometry.coordinates;
        const dist = calculateDistance(latitude, longitude, lat, lon);
        if (dist <= 500) {
          list.push({
            type: 'station',
            distance: dist,
            object: feat.properties,
            coords: { latitude: lat, longitude: lon }
          });
        }
      });
    }

    // Trier par distance croissante
    return list.sort((a, b) => a.distance - b.distance).slice(0, 10);
  };

  const nearby = getNearbyObjects();

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>📍 Équipements à proximité (&lt;500m)</Text>
        <TouchableOpacity onPress={onClose}>
          <Text style={styles.closeBtn}>X</Text>
        </TouchableOpacity>
      </View>

      {nearby.length > 0 ? (
        <FlatList
          data={nearby}
          keyExtractor={(item, idx) => idx.toString()}
          renderItem={({ item }) => (
            <View style={styles.itemRow}>
              <View style={styles.itemInfo}>
                <Text style={styles.itemTitle}>
                  {item.type === 'regard' ? '🕳️ Regard' : '⚙️ Station'} : {item.object.code || item.object.nom || item.object.id}
                </Text>
                <Text style={styles.itemDistance}>
                  Distance : {item.distance.toFixed(0)} mètres
                </Text>
                {item.object.commune && (
                  <Text style={styles.itemCommune}>{item.object.commune}</Text>
                )}
              </View>
              <TouchableOpacity
                style={styles.selectBtn}
                onPress={() => onSelect(item.object, item.type, item.coords)}
              >
                <Text style={styles.selectBtnText}>Inspecter</Text>
              </TouchableOpacity>
            </View>
          )}
        />
      ) : (
        <Text style={styles.emptyText}>Aucun regard ou équipement détecté à moins de 500m de votre position GPS.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#ddd', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  title: { fontSize: 14, fontWeight: 'bold', color: '#16213e' },
  closeBtn: { fontSize: 16, fontWeight: 'bold', color: '#888', padding: 4 },
  itemRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#eee' },
  itemInfo: { flex: 1 },
  itemTitle: { fontSize: 13, fontWeight: 'bold', color: '#333' },
  itemDistance: { fontSize: 11, color: '#e67e22', marginTop: 2, fontWeight: 'bold' },
  itemCommune: { fontSize: 11, color: '#888', marginTop: 1 },
  selectBtn: { backgroundColor: '#16213e', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4 },
  selectBtnText: { color: '#fff', fontSize: 11, fontWeight: 'bold' },
  emptyText: { color: '#666', fontStyle: 'italic', fontSize: 12, textAlign: 'center', marginTop: 20 }
});
