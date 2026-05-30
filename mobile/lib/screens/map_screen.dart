import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:swmm_mobile/services/api_service.dart';
import 'package:swmm_mobile/services/storage_service.dart';
import 'package:swmm_mobile/components/fiche_terrain.dart';
import 'package:swmm_mobile/components/incident_form.dart';
import 'package:swmm_mobile/components/scanner_sim.dart';
import 'package:swmm_mobile/components/proximite_list.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  Map<String, dynamic>? layers;
  bool loading = true;
  String networkMode = 'online';
  Position? userLocation;
  Map<String, dynamic>? activeObject;
  String activeType = 'regard';
  bool showProximite = false;
  bool showScanner = false;
  bool declaringIncident = false;
  LatLng? tempCoordinate;
  bool showIncidentForm = false;
  List<Map<String, dynamic>> localIncidents = [];

  @override
  void initState() {
    super.initState();
    loadInitialData();
  }

  Future<void> loadInitialData() async {
    try {
      setState(() => loading = true);
      final mode = await storageService.getNetworkMode();
      setState(() => networkMode = mode);
      final data = await apiService.getLayers();
      setState(() => layers = data);
      await requestGPSLocation();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Erreur lors du chargement de la carte')),
        );
      }
    } finally {
      setState(() => loading = false);
    }
  }

  Future<void> requestGPSLocation() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.whileInUse ||
          permission == LocationPermission.always) {
        final position = await Geolocator.getCurrentPosition();
        setState(() => userLocation = position);
      }
    } catch (e) {
      debugPrint('GPS non disponible');
    }
  }

  void centerOnUser() {
    if (userLocation == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Position GPS non encore détectée')),
      );
      return;
    }
  }

  Future<void> saveInspection(Map<String, dynamic> inspectionData) async {
    try {
      if (networkMode == 'online') {
        try {
          await apiService.post('/api/v1/terrain/inspections', inspectionData);
        } catch (_) {
          await storageService.addPendingChange({
            'type': 'inspection',
            ...inspectionData
          });
        }
      } else {
        await storageService.addPendingChange({
          'type': 'inspection',
          ...inspectionData
        });
      }
      setState(() => activeObject = null);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Inspection enregistrée avec succès !')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Erreur lors de l'enregistrement")),
        );
      }
    }
  }

  Future<void> saveIncident(Map<String, dynamic> incidentData) async {
    try {
      if (networkMode == 'online') {
        try {
          final result = await apiService.post('/api/v1/terrain/incidents', incidentData);
          setState(() => localIncidents.add(result));
        } catch (_) {
          final saved = await storageService.addPendingChange({
            'type': 'incident',
            ...incidentData
          });
          setState(() => localIncidents.add(saved));
        }
      } else {
        final saved = await storageService.addPendingChange({
          'type': 'incident',
          ...incidentData
        });
        setState(() => localIncidents.add(saved));
      }
      setState(() {
        showIncidentForm = false;
        tempCoordinate = null;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Incident signalé avec succès !')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Erreur lors de l'enregistrement de l'incident")),
        );
      }
    }
  }

  List<Map<String, dynamic>> getScannerTargets() {
    final list = <Map<String, dynamic>>[];
    if (layers?.containsKey('couches') == true) {
      final regards = layers!['couches']['regards']?['features'];
      if (regards != null && regards is List && regards.length > 5) {
        for (var i = 0; i < 5; i++) {
          final f = regards[i];
          list.add({
            'type': 'regard',
            'object': f['properties'],
          });
        }
      }
    }
    return list;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Carte du Réseau'),
      ),
      body: Stack(
        children: [
          FlutterMap(
            options: MapOptions(
              initialCenter: LatLng(36.15, 1.33),
              initialZoom: 12.0,
              onTap: (tapPosition, point) {
                if (declaringIncident) {
                  setState(() {
                    tempCoordinate = point;
                    showIncidentForm = true;
                    declaringIncident = false;
                  });
                }
              },
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                subdomains: const ['a', 'b', 'c'],
              ),
              if (layers?.containsKey('couches') == true) ...[
                MarkerLayer(
                  markers: [
                    if (layers!['couches']['regards']?['features'] != null)
                      ...List<Marker>.from(
                        (layers!['couches']['regards']['features'] as List)
                            .asMap()
                            .entries
                            .map((entry) {
                          final f = entry.value;
                          final coords = f['geometry']['coordinates'] as List;
                          return Marker(
                            point: LatLng(coords[1], coords[0]),
                            child: IconButton(
                              icon: const Icon(Icons.water, color: Color(0xFFf1c40f)),
                              onPressed: () {
                                setState(() {
                                  activeType = 'regard';
                                  activeObject = f['properties'];
                                });
                              },
                            ),
                          );
                        }),
                      ),
                    ...localIncidents.map((inc) => Marker(
                          point: LatLng(inc['latitude'], inc['longitude']),
                          child: const Icon(Icons.warning, color: Color(0xFFe74c3c)),
                        )),
                  ],
                ),
                PolylineLayer(
                  polylines: [
                    if (layers!['couches']['conduites']?['features'] != null)
                      ...(layers!['couches']['conduites']['features'] as List)
                          .map((f) {
                        final coords = f['geometry']['coordinates'] as List;
                        return Polyline(
                          points: coords
                              .map((c) => LatLng((c as List)[1], (c as List)[0]))
                              .toList(),
                          color: const Color(0xFF3498db),
                          strokeWidth: 5.0,
                        );
                      }),
                  ],
                ),
              ],
            ],
          ),
          Positioned(
            bottom: 20,
            left: 10,
            right: 10,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                FloatingActionButton(
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: centerOnUser,
                  child: const Text('📍', style: TextStyle(fontSize: 12)),
                ),
                FloatingActionButton(
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: () => setState(() => showProximite = true),
                  child: const Text('🔍', style: TextStyle(fontSize: 12)),
                ),
                FloatingActionButton(
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: () => setState(() => showScanner = true),
                  child: const Text('📷', style: TextStyle(fontSize: 12)),
                ),
                FloatingActionButton(
                  backgroundColor: declaringIncident
                      ? const Color(0xFFe74c3c)
                      : const Color(0xFF16213e),
                  onPressed: () => setState(() => declaringIncident = !declaringIncident),
                  child: const Text('🚨', style: TextStyle(fontSize: 12)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}