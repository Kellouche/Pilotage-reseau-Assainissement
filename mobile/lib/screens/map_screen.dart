import 'dart:async';
import 'dart:math' as math;

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
  List<Map<String, dynamic>> _cachedConduites = [];
  String editableLayer = 'Toutes'; // Toutes, Regards, Conduites

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

  void _handleMapTap(LatLng point) {
    if (declaringIncident) {
      setState(() {
        tempCoordinate = point;
        showIncidentForm = true;
        declaringIncident = false;
      });
      return;
    }

    if (currentZoom < 14 || _cachedConduites.isEmpty || editableLayer == 'Regards') {
      setState(() => activeObject = null);
      return;
    }

    const latMeters = 111320.0;
    final lngMeters = 111320.0 * math.cos(point.latitude * math.pi / 180.0);

    double minDistance = double.infinity;
    Map<String, dynamic>? closestConduite;

    for (final conduite in _cachedConduites) {
      final List<LatLng> points = conduite['points'];
      for (int i = 0; i < points.length - 1; i++) {
        final p1 = points[i];
        final p2 = points[i + 1];

        final x1 = (p1.longitude - point.longitude) * lngMeters;
        final y1 = (p1.latitude - point.latitude) * latMeters;
        final x2 = (p2.longitude - point.longitude) * lngMeters;
        final y2 = (p2.latitude - point.latitude) * latMeters;

        final double dx = x2 - x1;
        final double dy = y2 - y1;
        final double lenSq = dx * dx + dy * dy;

        double t = 0;
        if (lenSq != 0) {
          t = ((-x1) * dx + (-y1) * dy) / lenSq;
          t = t.clamp(0.0, 1.0);
        }

        final double projX = x1 + t * dx;
        final double projY = y1 + t * dy;

        final double distance = math.sqrt(projX * projX + projY * projY);

        if (distance < minDistance) {
          minDistance = distance;
          closestConduite = conduite['properties'];
        }
      }
    }

    // Seuil de détection : 30 mètres
    if (minDistance < 30.0 && closestConduite != null) {
      setState(() {
        activeType = 'conduite';
        activeObject = closestConduite;
      });
    } else {
      setState(() {
        activeObject = null;
      });
    }
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

  Future<void> _saveEditedObject(Map<String, dynamic> obj) async {
    final featureId = activeType == 'regard' ? (obj['id'] ?? obj['code']).toString() : (obj['id'] ?? obj['fid']).toString();
    final changes = {
      'type': 'update',
      'layer': activeType == 'regard' ? 'regards' : 'conduites',
      'feature_id': featureId,
      'changes': obj,
    };
    
    try {
      if (networkMode == 'online') {
        await syncService.pushChanges('mobile-device-001', [changes]);
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Modifications envoyées au serveur')));
      } else {
        await storageService.addPendingChange({
          'type': activeType,
          'object_id': featureId,
          ...obj
        });
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sauvegardé hors-ligne')));
      }
      setState(() => activeObject = null);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Erreur lors de la sauvegarde')));
    }
  }

  void _showEditDialog(Map<String, dynamic> obj, String title, List<String> editableKeys) {
    final Map<String, dynamic> tempObj = Map<String, dynamic>.from(obj);

    showDialog(
      context: context,
      builder: (BuildContext dialogContext) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1a1a2e),
          title: Text(title, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: editableKeys.map((key) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12.0),
                  child: TextFormField(
                    initialValue: tempObj[key]?.toString() ?? '',
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: key.toUpperCase(),
                      labelStyle: const TextStyle(color: Colors.white70, fontSize: 12),
                      enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
                    ),
                    onChanged: (val) {
                      if (obj[key] is int || tempObj[key] is int) {
                         tempObj[key] = int.tryParse(val) ?? tempObj[key];
                      } else if (obj[key] is double || tempObj[key] is double) {
                         tempObj[key] = double.tryParse(val) ?? tempObj[key];
                      } else {
                         tempObj[key] = val;
                      }
                    },
                  ),
                );
              }).toList(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Annuler', style: TextStyle(color: Colors.redAccent)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF27ae60),
                foregroundColor: Colors.white,
              ),
              onPressed: () {
                Navigator.of(dialogContext).pop();
                setState(() {
                  for (final key in editableKeys) {
                    activeObject![key] = tempObj[key];
                  }
                });
                _saveEditedObject(activeObject!);
              },
              child: const Text('Enregistrer'),
            ),
          ],
        );
      },
    );
  }

  Widget _buildObjectSummary() {
    final obj = activeObject!;
    final isRegard = activeType == 'regard';
    final title = isRegard ? 'Regard ${obj['code'] ?? obj['id']}' : 'Conduite ${obj['fid'] ?? obj['id']}';
    
    final excludedKeys = ['id', 'fid', 'code', 'geom', 'geom_geojson', 'type', 'gid'];
    final editableKeys = obj.keys.where((k) => !excludedKeys.contains(k.toLowerCase())).toList();

    final String summaryInfo = isRegard 
        ? 'Type: ${obj['type_regard'] ?? 'N/A'}\nProfondeur: ${obj['profondeur'] ?? 'N/A'} m'
        : 'Diamètre: ${obj['diametre'] ?? 'N/A'} mm\nMatériau: ${obj['materiau'] ?? 'N/A'}';

    return Positioned(
      bottom: 20,
      left: 20,
      right: 20,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1a1a2e).withOpacity(0.95),
          borderRadius: BorderRadius.circular(12),
          boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 10, offset: Offset(0, 4))],
          border: Border.all(color: Colors.white24)
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(isRegard ? Icons.circle : Icons.horizontal_rule, color: isRegard ? const Color(0xFF8E44AD) : const Color(0xFF3498db), size: 20),
                    const SizedBox(width: 8),
                    Text(title, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                  ],
                ),
                IconButton(
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  icon: const Icon(Icons.close, color: Colors.white70, size: 20),
                  onPressed: () => setState(() => activeObject = null),
                )
              ],
            ),
            const SizedBox(height: 8),
            Text(summaryInfo, style: const TextStyle(color: Colors.white70, height: 1.4)),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 36,
              child: ElevatedButton.icon(
                icon: const Icon(Icons.edit, size: 16),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF3498db),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                onPressed: () => _showEditDialog(obj, title, editableKeys),
                label: const Text('Modifier'),
              ),
            )
          ],
        ),
      ),
    );
  }

  Widget _buildIncidentForm() {
    String typeIncident = 'Fuite';
    String gravite = 'Moyenne';
    String description = '';

    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: const BoxDecoration(
          color: Color(0xFF1a1a2e),
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
          boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 10, offset: Offset(0, -2))],
        ),
        child: StatefulBuilder(
          builder: (context, setModalState) {
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('Déclarer un incident', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white70),
                      onPressed: () => setState(() => showIncidentForm = false),
                    )
                  ],
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  value: typeIncident,
                  dropdownColor: const Color(0xFF16213e),
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Type d\'incident', labelStyle: TextStyle(color: Colors.white70)),
                  items: ['Fuite', 'Obstruction', 'Rupture', 'Autre'].map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(),
                  onChanged: (v) => setModalState(() => typeIncident = v!),
                ),
                DropdownButtonFormField<String>(
                  value: gravite,
                  dropdownColor: const Color(0xFF16213e),
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Gravité', labelStyle: TextStyle(color: Colors.white70)),
                  items: ['Faible', 'Moyenne', 'Haute', 'Critique'].map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(),
                  onChanged: (v) => setModalState(() => gravite = v!),
                ),
                TextFormField(
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Description', labelStyle: TextStyle(color: Colors.white70)),
                  onChanged: (v) => description = v,
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFe74c3c), foregroundColor: Colors.white),
                    onPressed: () {
                      final data = {
                        'type_incident': typeIncident,
                        'gravite': gravite,
                        'description': description,
                        'latitude': tempCoordinate?.latitude,
                        'longitude': tempCoordinate?.longitude,
                        'date_signalement': DateTime.now().toIso8601String(),
                        'statut': 'À traiter'
                      };
                      saveIncident(data);
                    },
                    child: const Text('Envoyer le signalement'),
                  ),
                )
              ],
            );
          }
        ),
      ),
    );
  }

  Widget _buildProximiteDialog() {
    final int nbRegards = regardMarkers.length;
    final int nbConduites = _cachedConduites.length;
    
    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: const BoxDecoration(
          color: Color(0xFF1a1a2e),
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
          boxShadow: [BoxShadow(color: Colors.black54, blurRadius: 10, offset: Offset(0, -2))],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Statistiques de Proximité', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white70),
                  onPressed: () => setState(() => showProximite = false),
                )
              ],
            ),
            const SizedBox(height: 16),
            const Text('Objets visibles à l\'écran :', style: TextStyle(color: Colors.white70, fontSize: 14)),
            const SizedBox(height: 8),
            ListTile(
              leading: const Icon(Icons.circle, color: Color(0xFF8E44AD)),
              title: const Text('Regards', style: TextStyle(color: Colors.white)),
              trailing: Text('$nbRegards', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
            ListTile(
              leading: const Icon(Icons.horizontal_rule, color: Color(0xFF3498db)),
              title: const Text('Conduites', style: TextStyle(color: Colors.white)),
              trailing: Text('$nbConduites', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScannerDialog() {
    return Positioned(
      top: 0, bottom: 0, left: 0, right: 0,
      child: Container(
        color: Colors.black87,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 250, height: 250,
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFF27ae60), width: 3),
                borderRadius: BorderRadius.circular(16)
              ),
              child: const Center(
                child: Icon(Icons.qr_code_scanner, color: Color(0xFF27ae60), size: 100),
              ),
            ),
            const SizedBox(height: 30),
            const Text('Visez le QR Code du regard', style: TextStyle(color: Colors.white, fontSize: 18)),
            const SizedBox(height: 30),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF3498db), foregroundColor: Colors.white),
              onPressed: () {
                final targets = getScannerTargets();
                setState(() => showScanner = false);
                if (targets.isNotEmpty) {
                  setState(() {
                    activeType = targets[0]['type'];
                    activeObject = targets[0]['object'];
                  });
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Aucun objet proche trouvé pour simuler')));
                }
              },
              child: const Text('Simuler un Scan'),
            ),
            TextButton(
              onPressed: () => setState(() => showScanner = false),
              child: const Text('Annuler', style: TextStyle(color: Colors.white54)),
            )
          ],
        ),
      ),
    );
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
              onTap: (tapPosition, point) => _handleMapTap(point),
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
                    const SizedBox(height: 8),
                    const Text(
                      'Couche éditable :',
                      style: TextStyle(color: Colors.white70, fontSize: 11),
                    ),
                    DropdownButton<String>(
                      value: editableLayer,
                      dropdownColor: const Color(0xFF16213e),
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                      isDense: true,
                      underline: const SizedBox(),
                      icon: const Icon(Icons.arrow_drop_down, color: Colors.white70, size: 16),
                      items: ['Toutes', 'Regards', 'Conduites'].map((String value) {
                        return DropdownMenuItem<String>(
                          value: value,
                          child: Text(value),
                        );
                      }).toList(),
                      onChanged: (String? newValue) {
                        if (newValue != null) {
                          setState(() {
                            editableLayer = newValue;
                            activeObject = null; // Reset selection on change
                          });
                        }
                      },
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
          if (activeObject != null) _buildObjectSummary(),
          if (showScanner) _buildScannerDialog(),
          if (showProximite) _buildProximiteDialog(),
          if (showIncidentForm) _buildIncidentForm(),
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
            if (editableLayer == 'Conduites') return;
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
    _cachedConduites.clear();
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
          _cachedConduites.add({
            'properties': f['properties'],
            'points': points,
          });
        }
      } else if (type == 'MultiLineString') {
        for (final lineCoords in coords) {
          if (lineCoords is! List) continue;
          final points = _parseLineString(lineCoords);
          if (points.isNotEmpty) {
            polylines.add(Polyline(points: points, color: const Color(0xFF3498db), strokeWidth: 5.0));
            _cachedConduites.add({
              'properties': f['properties'],
              'points': points,
            });
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
