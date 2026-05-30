/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Simulateur de scanner de QR code / code-barres pour la démonstration mobile.
 * Offre un viseur dynamique et permet de sélectionner un objet du réseau 
 * à scanner pour ouvrir instantanément sa fiche terrain.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ScrollView,
} from 'react-native';

export default function ScannerSim({ targets, onScanSuccess, onClose }) {
  const [selectedTarget, setSelectedTarget] = useState(targets && targets.length > 0 ? targets[0] : null);

  const handleSimulateScan = () => {
    if (!selectedTarget) {
      Alert.alert('Info', 'Aucune cible à scanner disponible à proximité.');
      return;
    }

    Alert.alert(
      'Scan Réussi',
      `Équipement détecté : ${selectedTarget.type.toUpperCase()} ${selectedTarget.object.code || selectedTarget.object.fid}`,
      [
        {
          text: 'Ouvrir la fiche',
          onPress: () => onScanSuccess(selectedTarget.object, selectedTarget.type),
        }
      ]
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>📷 Scanner QR Code / Code Équipement</Text>
        <TouchableOpacity onPress={onClose}>
          <Text style={styles.closeBtn}>Fermer</Text>
        </TouchableOpacity>
      </View>

      {/* Viseur de caméra simulé */}
      <View style={styles.cameraPreview}>
        <View style={styles.reticle}>
          <View style={styles.cornerTopLeft} />
          <View style={styles.cornerTopRight} />
          <View style={styles.cornerBottomLeft} />
          <View style={styles.cornerBottomRight} />
          <View style={styles.laser} />
        </View>
        <Text style={styles.scanText}>Placer le code au centre du viseur</Text>
      </View>

      {/* Zone de contrôle */}
      <View style={styles.controlPanel}>
        <Text style={styles.label}>Équipements détectés par la caméra :</Text>
        
        {targets && targets.length > 0 ? (
          <ScrollView style={styles.targetList}>
            {targets.map((tgt, idx) => (
              <TouchableOpacity
                key={idx}
                style={[
                  styles.targetItem,
                  selectedTarget === tgt && styles.targetItemActive
                ]}
                onPress={() => setSelectedTarget(tgt)}
              >
                <Text style={[styles.targetText, selectedTarget === tgt && styles.targetTextActive]}>
                  {tgt.type === 'regard' ? '🕳️ Regard' : '🚰 Conduite'} : {tgt.object.code || tgt.object.fid}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        ) : (
          <Text style={styles.emptyText}>Aucun équipement visible à proximité.</Text>
        )}

        <TouchableOpacity
          style={[styles.scanButton, !selectedTarget && styles.scanButtonDisabled]}
          onPress={handleSimulateScan}
          disabled={!selectedTarget}
        >
          <Text style={styles.scanButtonText}>⚡ Simuler la détection QR</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a1a1a', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  title: { color: '#fff', fontSize: 15, fontWeight: 'bold' },
  closeBtn: { color: '#e74c3c', fontWeight: 'bold', fontSize: 14 },
  cameraPreview: { flex: 1.2, backgroundColor: '#000', borderRadius: 8, justifyContent: 'center', alignItems: 'center', position: 'relative', overflow: 'hidden' },
  reticle: { width: 180, height: 180, borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)', position: 'relative' },
  cornerTopLeft: { position: 'absolute', top: -2, left: -2, width: 20, height: 20, borderTopWidth: 4, borderLeftWidth: 4, borderColor: '#2ecc71' },
  cornerTopRight: { position: 'absolute', top: -2, right: -2, width: 20, height: 20, borderTopWidth: 4, borderRightWidth: 4, borderColor: '#2ecc71' },
  cornerBottomLeft: { position: 'absolute', bottom: -2, left: -2, width: 20, height: 20, borderBottomWidth: 4, borderLeftWidth: 4, borderColor: '#2ecc71' },
  cornerBottomRight: { position: 'absolute', bottom: -2, right: -2, width: 20, height: 20, borderBottomWidth: 4, borderRightWidth: 4, borderColor: '#2ecc71' },
  laser: { position: 'absolute', top: '50%', left: 0, right: 0, height: 2, backgroundColor: '#e74c3c', opacity: 0.8 },
  scanText: { color: '#aaa', fontSize: 12, marginTop: 20, fontWeight: 'bold' },
  controlPanel: { flex: 1, marginTop: 20 },
  label: { color: '#fff', fontSize: 13, fontWeight: 'bold', marginBottom: 10 },
  targetList: { maxHeight: 110, marginBottom: 15 },
  targetItem: { backgroundColor: '#2a2a2a', padding: 10, borderRadius: 6, marginBottom: 6 },
  targetItemActive: { backgroundColor: '#2ecc71' },
  targetText: { color: '#ccc', fontSize: 13 },
  targetTextActive: { color: '#000', fontWeight: 'bold' },
  emptyText: { color: '#888', fontStyle: 'italic', fontSize: 12, marginBottom: 20 },
  scanButton: { backgroundColor: '#2ecc71', padding: 14, borderRadius: 8, alignItems: 'center', marginTop: 5 },
  scanButtonDisabled: { backgroundColor: '#444' },
  scanButtonText: { color: '#fff', fontWeight: 'bold', fontSize: 14 }
});
