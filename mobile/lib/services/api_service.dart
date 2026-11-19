import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:flutter_map/flutter_map.dart';
import 'storage_service.dart';

class ApiService {
  final String baseUrl;
  
  ApiService({String? baseUrl}) 
      : baseUrl = baseUrl ??
            const String.fromEnvironment(
              'API_BASE_URL',
              defaultValue: 'http://127.0.0.1:5002',
            );

  Future<Map<String, String>> getHeaders([Map<String, String>? extra]) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    final token = await storageService.getAuthToken();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    if (extra != null) {
      headers.addAll(extra);
    }
    return headers;
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'email': email, 'password': password}),
    );
    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final token = data['access_token'] ?? data['token'];
      if (token != null) {
        await storageService.setAuthToken(token.toString());
      }
      return data;
    }
    throw Exception('Login failed: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getLayers({LatLngBounds? bounds}) async {
    final queryParameters = <String, String>{};
    if (bounds != null) {
      queryParameters.addAll({
        'ne_lat': bounds.northEast.latitude.toString(),
        'ne_lng': bounds.northEast.longitude.toString(),
        'sw_lat': bounds.southWest.latitude.toString(),
        'sw_lng': bounds.southWest.longitude.toString(),
      });
    }
    final uri = Uri.parse('$baseUrl/api/v1/layers').replace(
      queryParameters: queryParameters.isEmpty ? null : queryParameters,
    );
    final headers = await getHeaders();
    final response = await http.get(uri, headers: headers);
    if (response.statusCode == 200) {
      return compute(_decodeJson, response.body);
    }
    throw Exception('Failed to load layers: ${response.statusCode}');
  }

  // Helper method for compute
  static Map<String, dynamic> _decodeJson(String source) => json.decode(source);

  Future<Map<String, dynamic>> updateConduite(String conduiteId, Map<String, dynamic> updateData) async {
    final headers = await getHeaders();
    final response = await http.patch(
      Uri.parse('$baseUrl/api/v1/network/conduites/$conduiteId'),
      headers: headers,
      body: json.encode(updateData),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to update conduite: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> data) async {
    final headers = await getHeaders();
    final response = await http.post(
      Uri.parse('$baseUrl$endpoint'),
      headers: headers,
      body: json.encode(data),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return json.decode(response.body);
    }
    throw Exception('POST failed ($endpoint): ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getQualityScoresByBasin() async {
    final headers = await getHeaders();
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/qualite/scores-bassins'),
      headers: headers,
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load quality scores by basin: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> validateIncremental(List<int> conduitIds) async {
    final headers = await getHeaders();
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/qualite/valider-incremental'),
      headers: headers,
      body: json.encode({'ids_conduites': conduitIds}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to validate incremental: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getClusterGeojson(int clusterId) async {
    final headers = await getHeaders();
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/clusters/$clusterId/geojson'),
      headers: headers,
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load cluster geojson: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> analyseMntBasins() async {
    final headers = await getHeaders();
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/mnt/analyser-bassins'),
      headers: headers,
      body: json.encode({}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to analyse MNT basins: ${response.statusCode}');
  }
}

final apiService = ApiService();

class SyncService {
  final ApiService _api;
  
  SyncService(this._api);

  Future<Map<String, dynamic>> getDelta(int sinceVersion) async {
    final headers = await _api.getHeaders();
    final response = await http.get(
      Uri.parse('${_api.baseUrl}/api/v1/sync/delta?since_version=$sinceVersion'),
      headers: headers,
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to get delta: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> pushChanges(String deviceId, List<Map<String, dynamic>> changes) async {
    final headers = await _api.getHeaders();
    final response = await http.post(
      Uri.parse('${_api.baseUrl}/api/v1/sync/push'),
      headers: headers,
      body: json.encode({'device_id': deviceId, 'changes': changes}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to push changes: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> registerSession(String deviceId) async {
    final headers = await _api.getHeaders();
    final response = await http.post(
      Uri.parse('${_api.baseUrl}/api/v1/sync/session?device_id=$deviceId'),
      headers: headers,
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to register session: ${response.statusCode}');
  }
}

final syncService = SyncService(apiService);

class HealthService {
  final ApiService _api;
  
  HealthService(this._api);

  Future<Map<String, dynamic>> checkHealth() async {
    final response = await http.get(
      Uri.parse('${_api.baseUrl}/health'),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to check health: ${response.statusCode}');
  }
}

final healthService = HealthService(apiService);
