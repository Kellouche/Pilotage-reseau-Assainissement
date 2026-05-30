/**
 * Nom Auteur : Dr Abdelhakim Kellouche
 * Nom de l'application : Plateforme de Pilotage du Réseau d'Assainissement
 * Numéro version : 1.0.0
 * Date de création : 30-05-2026
 * Date de modification : 30-05-2026
 * 
 * Objectif du module :
 * Service de stockage local persistant pour gérer la file d'attente des modifications 
 * hors ligne (inspections, incidents, corrections) et le mode de connexion simulé.
 * Utilise AsyncStorage avec un fallback robuste en mémoire.
 */

// Fallback en mémoire au cas où AsyncStorage n'est pas initialisé ou disponible
const _memoryDb = {
  'NETWORK_MODE': 'online',
  'PENDING_CHANGES': '[]',
};

let AsyncStorage = null;
try {
  // Tenter de charger AsyncStorage de React Native
  AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {
  console.warn('[STORAGE] AsyncStorage non disponible. Utilisation du fallback en mémoire.');
}

const getItem = async (key) => {
  try {
    if (AsyncStorage) {
      const val = await AsyncStorage.getItem(key);
      return val;
    }
  } catch (error) {
    console.error(`[STORAGE] Erreur lecture key ${key}:`, error);
  }
  return _memoryDb[key] || null;
};

const setItem = async (key, value) => {
  try {
    if (AsyncStorage) {
      await AsyncStorage.setItem(key, value);
      return;
    }
  } catch (error) {
    console.error(`[STORAGE] Erreur écriture key ${key}:`, error);
  }
  _memoryDb[key] = value.toString();
};

export const storageService = {
  /**
   * Récupère le mode de connexion simulé ('online' ou 'offline')
   */
  async getNetworkMode() {
    const mode = await getItem('NETWORK_MODE');
    return mode || 'online';
  },

  /**
   * Modifie le mode de connexion simulé
   */
  async setNetworkMode(mode) {
    await setItem('NETWORK_MODE', mode);
  },

  /**
   * Récupère les modifications locales en attente de synchronisation
   */
  async getPendingChanges() {
    const changes = await getItem('PENDING_CHANGES');
    return changes ? JSON.parse(changes) : [];
  },

  /**
   * Ajoute une nouvelle modification à la file d'attente locale
   */
  async addPendingChange(change) {
    const changes = await this.getPendingChanges();
    // Générer un ID local si manquant
    const newChange = {
      localId: Date.now().toString() + Math.random().toString(36).substr(2, 5),
      timestamp: new Date().toISOString(),
      ...change,
    };
    changes.push(newChange);
    await setItem('PENDING_CHANGES', JSON.stringify(changes));
    return newChange;
  },

  /**
   * Supprime une modification de la file d'attente locale par son ID local
   */
  async removePendingChange(localId) {
    let changes = await this.getPendingChanges();
    changes = changes.filter(c => c.localId !== localId);
    await setItem('PENDING_CHANGES', JSON.stringify(changes));
  },

  /**
   * Vide complètement la file d'attente locale
   */
  async clearPendingChanges() {
    await setItem('PENDING_CHANGES', '[]');
  }
};

export default storageService;
