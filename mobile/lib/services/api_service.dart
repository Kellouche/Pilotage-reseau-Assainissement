import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:flutter_map/flutter_map.dart';

class ApiService {
  final String baseUrl;
  
  ApiService({String? baseUrl}) 
      : baseUrl = baseUrl ??
            const String.fromEnvironment(
              'API_BASE_URL',
              defaultValue: 'http://10.0.2.2:5001',
            );

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
    final response = await http.get(uri);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load layers');
  }

  Future<Map<String, dynamic>> updateConduite(String conduiteId, Map<String, dynamic> updateData) async {
    final response = await http.patch(
      Uri.parse('$baseUrl/api/v1/network/conduites/$conduiteId'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode(updateData),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to update conduite');
  }

  Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> data) async {
    final response = await http.post(
      Uri.parse('$baseUrl$endpoint'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode(data),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('POST failed: $endpoint');
  }
}

final apiService = ApiService();

class SyncService {
  Future<Map<String, dynamic>> getDelta(int sinceVersion) async {
    final response = await http.get(
      Uri.parse('http://127.0.0.1:5001/api/v1/sync/delta?since_version=$sinceVersion'),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to get delta');
  }

  Future<Map<String, dynamic>> pushChanges(String deviceId, List<Map<String, dynamic>> changes) async {
    final response = await http.post(
      Uri.parse('http://127.0.0.1:5001/api/v1/sync/push'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'device_id': deviceId, 'changes': changes}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to push changes');
  }

  Future<Map<String, dynamic>> registerSession(String deviceId) async {
    final response = await http.post(
      Uri.parse('http://127.0.0.1:5001/api/v1/sync/session?device_id=$deviceId'),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to register session');
  }
}

final syncService = SyncService();

class HealthService {
  Future<Map<String, dynamic>> checkHealth() async {
    final response = await http.get(
      Uri.parse('http://127.0.0.1:5001/health'),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to check health');
  }
}
