import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:swmm_mobile/services/api_service.dart';
import 'package:swmm_mobile/services/storage_service.dart';

class _LegendItem extends StatelessWidget {
  final String label;
  final Color? color;
  final bool isActive;

  const _LegendItem({
    required this.label,
    this.color,
    this.isActive = true,
  });

  @override
  Widget build(BuildContext context) {
    final itemColor = isActive ? Colors.white : Colors.white70;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (color != null)
            Container(
              width: 16,
              height: 16,
              decoration: BoxDecoration(
                color: isActive ? color : color!.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: itemColor, width: 1),
              ),
            )
          else
            Icon(Icons.info_outline, size: 16, color: itemColor),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(color: itemColor, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController mapController = MapController();
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
  List<Marker> regardMarkers = [];
  List<Polyline> conduitePolylines = [];

  LatLngBounds? currentBounds;
  double currentZoom = 13.0;
  String? lastFetchCacheKey;
  Timer? _debounceTimer;
  int _zoomDisplayBucket = 0;
  static const Duration debounceDuration = Duration(milliseconds: 900);

  @override
  void initState() {
    super.initState();
    loadInitialData();
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    super.dispose();
  }

  Future<void> loadInitialData() async {
    try {
      if (layers == null) {
        setState(() => loading = true);
      }
      final mode = await storageService.getNetworkMode();
      setState(() => networkMode = mode);

      final defaultBounds = LatLngBounds(
        LatLng(36.15 - 0.05, 1.33 - 0.05),
        LatLng(36.15 + 0.05, 1.33 + 0.05),
      );
      await loadMapData(bounds: defaultBounds);
      await requestGPSLocation();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Erreur lors du chargement de la carte')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
    }
  }

  Future<void> loadMapData({LatLngBounds? bounds, bool force = false}) async {
    if (!mounted) return;

    try {
      final cacheKey = bounds == null ? 'all-layers' : _boundsCacheKey(bounds);

      if (!force && cacheKey == lastFetchCacheKey) return;

      if (layers == null) {
        setState(() => loading = true);
      }
      final data = await apiService.getLayers(bounds: bounds);
      final parsedRegards = _parseRegardMarkers(data);
      final parsedConduites = _parseConduitePolylines(data);

      setState(() {
        layers = data;
        currentBounds = bounds ?? currentBounds;
        lastFetchCacheKey = cacheKey;
        regardMarkers = parsedRegards;
        conduitePolylines = parsedConduites;
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Erreur lors du chargement de la carte')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
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
        if (mounted) {
          setState(() => userLocation = position);
        }
      }
    } catch (_) {
      debugPrint('GPS non disponible');
    }
  }

  void _onMapMoved(MapCamera camera, bool hasGesture) {
    if (!mounted) return;

    final newBucket = _zoomBucket(camera.zoom);
    final shouldRefreshUi =
        newBucket != _zoomDisplayBucket || (camera.zoom - currentZoom).abs() > 0.25;

    currentBounds = camera.visibleBounds;
    currentZoom = camera.zoom;

    if (hasGesture) {
      _debounceTimer?.cancel();
      _debounceTimer = Timer(debounceDuration, () {
        if (mounted && currentBounds != null) {
          loadMapData(bounds: currentBounds);
        }
      });
    }

    if (shouldRefreshUi) {
      setState(() {
        _zoomDisplayBucket = newBucket;
        if (layers != null) {
          regardMarkers = _parseRegardMarkers(layers!);
          conduitePolylines = _parseConduitePolylines(layers!);
        }
      });
    }
  }

  void centerOnUser() {
    if (userLocation == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Position GPS non encore detectee')),
      );
      return;
    }
    mapController.move(
      LatLng(userLocation!.latitude, userLocation!.longitude),
      15.0,
    );
  }

  Future<void> saveInspection(Map<String, dynamic> inspectionData) async {
    try {
      if (networkMode == 'online') {
        try {
          await apiService.post('/api/v1/terrain/inspections', inspectionData);
        } catch (_) {
          await storageService
              .addPendingChange({'type': 'inspection', ...inspectionData});
        }
      } else {
        await storageService
            .addPendingChange({'type': 'inspection', ...inspectionData});
      }

      setState(() => activeObject = null);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Inspection enregistree avec succes !')),
        );
      }
    } catch (_) {
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
          final result =
              await apiService.post('/api/v1/terrain/incidents', incidentData);
          setState(() => localIncidents.add(result));
        } catch (_) {
          final saved = await storageService
              .addPendingChange({'type': 'incident', ...incidentData});
          setState(() => localIncidents.add(saved));
        }
      } else {
        final saved = await storageService
            .addPendingChange({'type': 'incident', ...incidentData});
        setState(() => localIncidents.add(saved));
      }

      setState(() {
        showIncidentForm = false;
        tempCoordinate = null;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Incident signale avec succes !')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("Erreur lors de l'enregistrement de l'incident"),
          ),
        );
      }
    }
  }

  List<Map<String, dynamic>> getScannerTargets() {
    final list = <Map<String, dynamic>>[];
    final regards = layers?['couches']?['regards']?['features'];
    if (regards is List && regards.length > 5) {
      for (var i = 0; i < 5; i++) {
        final f = regards[i];
        list.add({
          'type': 'regard',
          'object': f['properties'],
        });
      }
    }
    return list;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Carte du Reseau'),
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: mapController,
            options: MapOptions(
              initialCenter: LatLng(36.15, 1.33),
              initialZoom: 13.0,
              onTap: (tapPosition, point) {
                if (declaringIncident) {
                  setState(() {
                    tempCoordinate = point;
                    showIncidentForm = true;
                    declaringIncident = false;
                  });
                }
              },
              onPositionChanged: _onMapMoved,
            ),
            children: [
              TileLayer(
                urlTemplate:
                    'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                subdomains: const ['a', 'b', 'c'],
              ),
              if (layers != null) ...[
                if (currentZoom >= 13)
                  MarkerLayer(
                    markers: [
                      ...regardMarkers,
                      ..._buildIncidentMarkers(),
                    ],
                  ),
                if (currentZoom >= 14)
                  PolylineLayer(polylines: conduitePolylines),
              ],
            ],
          ),
          if (loading)
            const Positioned.fill(
              child: ColoredBox(
                color: Colors.black54,
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(color: Colors.white),
                      SizedBox(height: 16),
                      Text(
                        'Chargement des donnees cartographiques...',
                        style: TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Positioned(
            top: 12,
            left: 10,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: const Color(0xDD16213e),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white24),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Zoom ${currentZoom.toStringAsFixed(1)}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    _LegendItem(
                      label: 'Regards (${layers?['compteurs']?['regards'] ?? 0})',
                      color: const Color(0xFF8E44AD),
                      isActive: currentZoom >= 13,
                    ),
                    _LegendItem(
                      label: 'Conduites (${layers?['compteurs']?['conduites'] ?? 0})',
                      color: const Color(0xFF3498db),
                      isActive: currentZoom >= 14,
                    ),
                    if (currentZoom < 13)
                      const _LegendItem(
                        label: 'Zoomez pour afficher les objets',
                        isActive: false,
                      ),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            bottom: 20,
            right: 10,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                FloatingActionButton(
                  heroTag: 'fab_location',
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: centerOnUser,
                  child: const Icon(Icons.my_location, color: Colors.white),
                ),
                const SizedBox(width: 8),
                FloatingActionButton(
                  heroTag: 'fab_search',
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: () => setState(() => showProximite = true),
                  child: const Icon(Icons.search, color: Colors.white),
                ),
                const SizedBox(width: 8),
                FloatingActionButton(
                  heroTag: 'fab_scanner',
                  backgroundColor: const Color(0xFF16213e),
                  onPressed: () => setState(() => showScanner = true),
                  child: const Icon(Icons.qr_code_scanner, color: Colors.white),
                ),
                const SizedBox(width: 8),
                FloatingActionButton(
                  heroTag: 'fab_incident',
                  backgroundColor: declaringIncident
                      ? const Color(0xFFe74c3c)
                      : const Color(0xFF16213e),
                  onPressed: () =>
                      setState(() => declaringIncident = !declaringIncident),
                  child: const Icon(Icons.warning, color: Colors.white),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _boundsCacheKey(LatLngBounds bounds) {
    return '${bounds.northEast.latitude.toStringAsFixed(4)}|'
        '${bounds.northEast.longitude.toStringAsFixed(4)}|'
        '${bounds.southWest.latitude.toStringAsFixed(4)}|'
        '${bounds.southWest.longitude.toStringAsFixed(4)}';
  }

  int _zoomBucket(double zoom) {
    if (zoom >= 15) return 3;
    if (zoom >= 14) return 2;
    if (zoom >= 13) return 1;
    return 0;
  }

  List<Marker> _parseRegardMarkers(Map<String, dynamic> data) {
    if (currentZoom < 13) return []; // Match the rendering condition to avoid parsing when not displayed
    final features = data['couches']?['regards']?['features'];
    if (features is! List) return [];

    // zoom 13: rayon 1px (diam 2), zoom 14: rayon 2px (diam 4)
    // zoom 15: rayon 3px (diam 6), zoom >= 16: rayon 4px (diam 8)
    final double diameter = (currentZoom - 12.0).clamp(1.0, 4.0) * 2.0;

    return features.map((f) {
      final geom = f['geometry'];
      if (geom is! Map || !geom.containsKey('coordinates')) return null;
      final coords = geom['coordinates'];
      if (coords is! List || coords.length < 2) return null;
      if (coords[1] is! num || coords[0] is! num) return null;

      return Marker(
        width: diameter,
        height: diameter,
        point: LatLng(
          (coords[1] as num).toDouble(),
          (coords[0] as num).toDouble(),
        ),
        child: GestureDetector(
          onTap: () {
            setState(() {
              activeType = 'regard';
              activeObject = f['properties'];
            });
          },
          child: const DecoratedBox(
            decoration: BoxDecoration(
              color: Color(0xFF8E44AD), // Violet
              shape: BoxShape.circle,
            ),
          ),
        ),
      );
    }).whereType<Marker>().toList();
  }

  List<Marker> _buildIncidentMarkers() {
    return localIncidents.map((inc) {
      if (inc['latitude'] is! num || inc['longitude'] is! num) return null;

      return Marker(
        point: LatLng(
          (inc['latitude'] as num).toDouble(),
          (inc['longitude'] as num).toDouble(),
        ),
        child: const Icon(Icons.warning, color: Color(0xFFe74c3c)),
      );
    }).whereType<Marker>().toList();
  }

  List<Polyline> _parseConduitePolylines(Map<String, dynamic> data) {
    if (currentZoom < 14) return []; // Too zoomed out, don't freeze UI
    final features = data['couches']?['conduites']?['features'];
    if (features is! List) return [];

    final polylines = <Polyline>[];
    for (final f in features) {
      final geom = f['geometry'];
      if (geom is! Map || !geom.containsKey('coordinates')) continue;
      final type = geom['type'];
      final coords = geom['coordinates'];
      if (coords is! List) continue;

      if (type == 'LineString') {
        final points = _parseLineString(coords);
        if (points.isNotEmpty) {
          polylines.add(Polyline(points: points, color: const Color(0xFF3498db), strokeWidth: 5.0));
        }
      } else if (type == 'MultiLineString') {
        for (final lineCoords in coords) {
          if (lineCoords is! List) continue;
          final points = _parseLineString(lineCoords);
          if (points.isNotEmpty) {
            polylines.add(Polyline(points: points, color: const Color(0xFF3498db), strokeWidth: 5.0));
          }
        }
      }
    }
    return polylines;
  }

  List<LatLng> _parseLineString(List coords) {
    final points = <LatLng>[];
    for (final coord in coords) {
      if (coord is! List || coord.length < 2) continue;
      if (coord[1] is! num || coord[0] is! num) continue;
      points.add(LatLng((coord[1] as num).toDouble(), (coord[0] as num).toDouble()));
    }
    return points;
  }
}
