import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'dart:math' as math;

double calculateDistance(double lat1, double lon1, double lat2, double lon2) {
  if (lat1 == null || lon1 == null || lat2 == null || lon2 == null) return 999999;
  const r = 6371e3;
  final phi1 = lat1 * math.pi / 180;
  final phi2 = lat2 * math.pi / 180;
  final deltaPhi = (lat2 - lat1) * math.pi / 180;
  final deltaLambda = (lon2 - lon1) * math.pi / 180;

  final a = math.sin(deltaPhi / 2) * math.sin(deltaPhi / 2) +
      math.cos(phi1) * math.cos(phi2) * math.sin(deltaLambda / 2) * math.sin(deltaLambda / 2);
  final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));

  return r * c;
}

class ProximiteList extends StatelessWidget {
  final Map<String, dynamic> location;
  final Map<String, dynamic>? networkData;
  final VoidCallback onClose;
  final void Function(Map<String, dynamic> object, String type, LatLng coords) onSelect;

  const ProximiteList({
    super.key,
    required this.location,
    required this.networkData,
    required this.onClose,
    required this.onSelect,
  });

  List<Map<String, dynamic>> getNearbyObjects() {
    final list = <Map<String, dynamic>>[];
    final latitude = location['latitude'] as double;
    final longitude = location['longitude'] as double;

    if (networkData?.containsKey('couches') == true) {
      final regards = networkData!['couches']['regards']?['features'];
      if (regards != null && regards is List) {
        for (final feat in regards) {
          final coords = feat['geometry']['coordinates'] as List<dynamic>;
          final dist = calculateDistance(latitude, longitude, coords[1], coords[0]);
          if (dist <= 500) {
            list.add({
              'type': 'regard',
              'distance': dist,
              'object': feat['properties'],
              'coords': LatLng(coords[1], coords[0]),
            });
          }
        }
      }

      final stations = networkData!['couches']['stations']?['features'];
      if (stations != null && stations is List) {
        for (final feat in stations) {
          final coords = feat['geometry']['coordinates'] as List<dynamic>;
          final dist = calculateDistance(latitude, longitude, coords[1], coords[0]);
          if (dist <= 500) {
            list.add({
              'type': 'station',
              'distance': dist,
              'object': feat['properties'],
              'coords': LatLng(coords[1], coords[0]),
            });
          }
        }
      }
    }

    list.sort((a, b) => (a['distance'] as double).compareTo(b['distance'] as double));
    return list.take(10).toList();
  }

  @override
  Widget build(BuildContext context) {
    final nearby = getNearbyObjects();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Équipements à proximité (<500m)'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: onClose,
        ),
      ),
      body: nearby.isNotEmpty
          ? ListView.builder(
              itemCount: nearby.length,
              itemBuilder: (context, index) {
                final item = nearby[index];
                return ListTile(
                  contentPadding: const EdgeInsets.symmetric(vertical: 4, horizontal: 16),
                  title: Text(
                    item['type'] == 'regard'
                        ? '🕳️ Regard : ${item['object']['code'] ?? item['object']['nom'] ?? item['object']['id']}'
                        : '⚙️ Station : ${item['object']['code'] ?? item['object']['nom'] ?? item['object']['id']}',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Distance : ${(item['distance'] as double).toStringAsFixed(0)} mètres',
                        style: const TextStyle(
                          fontSize: 11,
                          color: Color(0xFFe67e22),
                        ),
                      ),
                      if (item['object']['commune'] != null)
                        Text(
                          item['object']['commune'] as String,
                          style: const TextStyle(fontSize: 11, color: Colors.grey),
                        ),
                    ],
                  ),
                  trailing: ElevatedButton(
                    onPressed: () => onSelect(
                      item['object'],
                      item['type'] as String,
                      item['coords'] as LatLng,
                    ),
                    child: const Text('Inspecter'),
                  ),
                );
              },
            )
          : const Center(
              child: Text(
                'Aucun regard ou équipement détecté à moins de 500m de votre position GPS.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
    );
  }