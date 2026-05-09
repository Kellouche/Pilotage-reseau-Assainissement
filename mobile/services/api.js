import axios from 'axios';

// Configuration de l'API
const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5001';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Service pour les couches réseau
export const networkService = {
  async getLayers() {
    try {
      const response = await api.get('/api/v1/layers');
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la récupération des couches:', error);
      throw error;
    }
  },

  async updateConduite(conduiteId, updateData) {
    try {
      const response = await api.patch(`/api/v1/network/conduites/${conduiteId}`, updateData);
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la mise à jour de la conduite:', error);
      throw error;
    }
  },
};

// Service pour les clusters
export const clusterService = {
  async detectClusters() {
    try {
      const response = await api.post('/api/v1/clusters/recalculate-all');
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la détection des clusters:', error);
      throw error;
    }
  },
};

// Service de synchronisation
export const syncService = {
  async getDelta(sinceVersion = 0) {
    try {
      const response = await api.get('/api/v1/sync/delta', {
        params: { since_version: sinceVersion }
      });
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la synchronisation delta:', error);
      throw error;
    }
  },

  async pushChanges(changes) {
    try {
      const response = await api.post('/api/v1/sync/push', {
        changes: changes
      });
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la poussée des changements:', error);
      throw error;
    }
  },

  async registerSession(deviceId) {
    try {
      const response = await api.post('/api/v1/sync/session', null, {
        params: { device_id: deviceId }
      });
      return response.data;
    } catch (error) {
      console.error('Erreur lors de l\'enregistrement de session:', error);
      throw error;
    }
  },
};

// Service de santé
export const healthService = {
  async checkHealth() {
    try {
      const response = await api.get('/health');
      return response.data;
    } catch (error) {
      console.error('Erreur lors de la vérification de santé:', error);
      throw error;
    }
  },
};

export default api;
