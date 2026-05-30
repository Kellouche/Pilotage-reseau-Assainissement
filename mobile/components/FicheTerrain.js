/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Composant de formulaire d'inspection terrain et fiche technique unifiée pour 
 * les regards, conduites, stations de relevage et ouvrages spéciaux.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Switch,
  Alert,
  Image,
} from 'react-native';

export default function FicheTerrain({ object, type, onSave, onClose }) {
  const [etat, setEtat] = useState('Bon');
  const [niveauEau, setNiveauEau] = useState('Normal');
  const [obstruction, setObstruction] = useState('Aucune');
  const [odeur, setOdeur] = useState('Aucune');
  const [debordement, setDebordement] = useState(false);
  const [commentaires, setCommentaires] = useState('');
  const [photos, setPhotos] = useState([]);
  const [statut, setStatut] = useState('À vérifier');

  // Simulation d'ajout de photo réaliste d'inspection
  const handleAddPhoto = () => {
    const mockPhotos = [
      'https://images.unsplash.com/photo-1542060748-10c28b629f6f?w=400', // canalisation
      'https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=400', // regard/plaque
      'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=400', // travaux/terrain
    ];
    const randomPhoto = mockPhotos[Math.floor(Math.random() * mockPhotos.length)];
    const newPhoto = `${randomPhoto}&sig=${Date.now()}`;
    setPhotos([...photos, newPhoto]);
  };

  const handleSave = () => {
    const inspectionData = {
      object_type: type,
      object_id: object.code || object.fid || object.id?.toString(),
      etat,
      niveau_eau: niveauEau,
      obstruction,
      odeur,
      debordement,
      commentaires,
      photos,
      statut,
      date_inspection: new Date().toISOString(),
    };
    onSave(inspectionData);
    Alert.alert('Succès', 'Inspection enregistrée avec succès !');
  };

  const renderDropdown = (label, current, options, setter) => (
    <View style={styles.formGroup}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.optionContainer}>
        {options.map((opt) => (
          <TouchableOpacity
            key={opt}
            style={[styles.optionButton, current === opt && styles.optionButtonActive]}
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
        <Text style={styles.title}>Fiche Terrain - {type.toUpperCase()}</Text>
        <Text style={styles.subtitle}>ID : {object.code || object.fid || object.id}</Text>
      </View>

      {/* Fiche Technique */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Fiche Technique</Text>
        {object.diametre && <Text style={styles.infoText}>• Diamètre : {object.diametre} mm</Text>}
        {object.longueur && <Text style={styles.infoText}>• Longueur : {object.longueur} m</Text>}
        {object.materiau && <Text style={styles.infoText}>• Matériau : {object.materiau}</Text>}
        {object.profondeur && <Text style={styles.infoText}>• Profondeur : {object.profondeur} m</Text>}
        {object.commune && <Text style={styles.infoText}>• Commune : {object.commune}</Text>}
        {object.nom_voie && <Text style={styles.infoText}>• Voie : {object.nom_voie}</Text>}
      </View>

      {/* Formulaire d'inspection */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Observations terrain</Text>
        
        {renderDropdown('État général', etat, ['Bon', 'Moyen', 'Mauvais'], setEtat)}
        {renderDropdown("Niveau d'eau", niveauEau, ['Vide', 'Normal', 'Sous charge', 'Débordement'], setNiveauEau)}
        {renderDropdown('Obstruction', obstruction, ['Aucune', 'Partielle', 'Totale'], setObstruction)}
        {renderDropdown('Odeur', odeur, ['Aucune', 'Légère', 'Forte'], setOdeur)}

        <View style={styles.formRow}>
          <Text style={styles.label}>Débordement actif :</Text>
          <Switch value={debordement} onValueChange={setDebordement} trackColor={{ true: '#e74c3c' }} />
        </View>

        {renderDropdown('Statut de validation', statut, ['À vérifier', 'Corrigé terrain', 'Validé bureau'], setStatut)}

        <Text style={styles.label}>Commentaires / Diagnostic :</Text>
        <TextInput
          style={styles.textInput}
          multiline
          numberOfLines={3}
          value={commentaires}
          onChangeText={setCommentaires}
          placeholder="Renseigner les constatations terrain..."
        />

        {/* Photos d'inspection */}
        <Text style={styles.label}>Photos d'inspection ({photos.length})</Text>
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
          <Text style={styles.btnTextSave}>Enregistrer</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9f9f9', padding: 12 },
  header: { backgroundColor: '#16213e', padding: 16, borderRadius: 8, marginBottom: 12 },
  title: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  subtitle: { color: '#ddd', fontSize: 14, marginTop: 4 },
  card: { backgroundColor: '#fff', padding: 16, borderRadius: 8, marginBottom: 12, elevation: 1 },
  cardTitle: { fontSize: 15, fontWeight: 'bold', color: '#16213e', marginBottom: 10, borderBottomWidth: 1, borderBottomColor: '#eee', paddingBottom: 6 },
  infoText: { fontSize: 13, color: '#555', marginBottom: 4 },
  formGroup: { marginBottom: 12 },
  label: { fontSize: 13, fontWeight: 'bold', color: '#333', marginBottom: 6 },
  optionContainer: { flexDirection: 'row', flexWrap: 'wrap' },
  optionButton: { backgroundColor: '#f0f0f0', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 4, marginRight: 6, marginBottom: 6 },
  optionButtonActive: { backgroundColor: '#16213e' },
  optionText: { fontSize: 12, color: '#555' },
  optionTextActive: { color: '#fff', fontWeight: 'bold' },
  formRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginVertical: 8 },
  textInput: { borderWidth: 1, borderColor: '#ddd', borderRadius: 4, padding: 8, fontSize: 13, backgroundColor: '#fafafa', textAlignVertical: 'top', minHeight: 60, marginBottom: 12 },
  photoGrid: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', marginTop: 6 },
  thumbnail: { width: 50, height: 50, borderRadius: 4, marginRight: 8, marginBottom: 8 },
  addPhotoBtn: { width: 50, height: 50, borderRadius: 4, borderWidth: 1, borderStyle: 'dashed', borderColor: '#888', justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
  addPhotoText: { fontSize: 9, fontWeight: 'bold', color: '#555', textAlign: 'center' },
  buttons: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, marginBottom: 40 },
  btn: { flex: 1, padding: 12, borderRadius: 6, alignItems: 'center', marginHorizontal: 4 },
  btnCancel: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#888' },
  btnSave: { backgroundColor: '#27ae60' },
  btnTextCancel: { color: '#555', fontWeight: 'bold' },
  btnTextSave: { color: '#fff', fontWeight: 'bold' }
});
