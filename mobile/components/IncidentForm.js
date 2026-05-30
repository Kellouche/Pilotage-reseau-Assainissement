/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Formulaire mobile de création et de déclaration d'incidents géolocalisés 
 * constatés sur le réseau d'assainissement (débordement, effondrement, odeur).
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Alert,
  Image,
} from 'react-native';

export default function IncidentForm({ coordinate, onSave, onClose }) {
  const [typeIncident, setTypeIncident] = useState('Débordement');
  const [gravite, setGravite] = useState('Moyenne');
  const [description, setDescription] = useState('');
  const [photos, setPhotos] = useState([]);

  const handleAddPhoto = () => {
    const mockPhotos = [
      'https://images.unsplash.com/photo-1541604193435-22419d562287?w=400', // eau croupie/inondation
      'https://images.unsplash.com/photo-1517649763962-0c623066013b?w=400', // rue/caniveaux bouchés
    ];
    const randomPhoto = mockPhotos[Math.floor(Math.random() * mockPhotos.length)];
    const newPhoto = `${randomPhoto}&sig=${Date.now()}`;
    setPhotos([...photos, newPhoto]);
  };

  const handleSave = () => {
    if (!description.trim()) {
      Alert.alert('Erreur', 'Veuillez saisir une description de l\'incident');
      return;
    }

    const incidentData = {
      type_incident: typeIncident,
      gravite,
      description,
      longitude: coordinate.longitude,
      latitude: coordinate.latitude,
      statut: 'À traiter',
      photos,
      date_creation: new Date().toISOString(),
    };

    onSave(incidentData);
    Alert.alert('Succès', 'Incident signalé avec succès !');
  };

  const renderOption = (label, current, options, setter) => (
    <View style={styles.formGroup}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.optionContainer}>
        {options.map((opt) => (
          <TouchableOpacity
            key={opt}
            style={[styles.optionBtn, current === opt && styles.optionBtnActive]}
            onPress={() => setter(opt)}
          >
            <Text style={[styles.optionText, current === opt && styles.optionTextActive]}>{opt}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>🚨 Signaler un Incident</Text>
        <Text style={styles.subtitle}>
          Coordonnées : {coordinate.latitude.toFixed(6)}, {coordinate.longitude.toFixed(6)}
        </Text>
      </View>

      <View style={styles.card}>
        {renderOption('Type d\'incident', typeIncident, ['Débordement', 'Obstruction', 'Odeur suspecte', 'Effondrement', 'Autre'], setTypeIncident)}
        {renderOption('Niveau de gravité', gravite, ['Faible', 'Moyenne', 'Haute', 'Critique'], setGravite)}

        <Text style={styles.label}>Description précise :</Text>
        <TextInput
          style={styles.textInput}
          multiline
          numberOfLines={3}
          value={description}
          onChangeText={setDescription}
          placeholder="Décrivez l'anomalie ou l'incident constaté sur place..."
        />

        <Text style={styles.label}>Photos de l'incident ({photos.length})</Text>
        <View style={styles.photoGrid}>
          {photos.map((uri, idx) => (
            <Image key={idx} source={{ uri }} style={styles.thumbnail} />
          ))}
          <TouchableOpacity style={styles.addPhotoBtn} onPress={handleAddPhoto}>
            <Text style={styles.addPhotoText}>📸 + Photo</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.buttons}>
        <TouchableOpacity style={[styles.btn, styles.btnCancel]} onPress={onClose}>
          <Text style={styles.btnTextCancel}>Annuler</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.btn, styles.btnSave]} onPress={handleSave}>
          <Text style={styles.btnTextSave}>Signaler</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9f9f9', padding: 12 },
  header: { backgroundColor: '#c0392b', padding: 16, borderRadius: 8, marginBottom: 12 },
  title: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  subtitle: { color: '#fcdcd9', fontSize: 12, marginTop: 4 },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 12, elevation: 1 },
  formGroup: { marginBottom: 12 },
  label: { fontSize: 13, fontWeight: 'bold', color: '#333', marginBottom: 6 },
  optionContainer: { flexDirection: 'row', flexWrap: 'wrap' },
  optionBtn: { backgroundColor: '#f0f0f0', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 4, marginRight: 6, marginBottom: 6 },
  optionBtnActive: { backgroundColor: '#c0392b' },
  optionText: { fontSize: 12, color: '#555' },
  optionTextActive: { color: '#fff', fontWeight: 'bold' },
  textInput: { borderWidth: 1, borderColor: '#ddd', borderRadius: 4, padding: 8, fontSize: 13, backgroundColor: '#fafafa', textAlignVertical: 'top', minHeight: 60, marginBottom: 12 },
  photoGrid: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', marginTop: 6 },
  thumbnail: { width: 50, height: 50, borderRadius: 4, marginRight: 8, marginBottom: 8 },
  addPhotoBtn: { width: 50, height: 50, borderRadius: 4, borderWidth: 1, borderStyle: 'dashed', borderColor: '#888', justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
  addPhotoText: { fontSize: 9, fontWeight: 'bold', color: '#555', textAlign: 'center' },
  buttons: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, marginBottom: 40 },
  btn: { flex: 1, padding: 12, borderRadius: 6, alignItems: 'center', marginHorizontal: 4 },
  btnCancel: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#888' },
  btnSave: { backgroundColor: '#c0392b' },
  btnTextCancel: { color: '#555', fontWeight: 'bold' },
  btnTextSave: { color: '#fff', fontWeight: 'bold' }
});
