import 'package:flutter/material.dart';

class ScannerSim extends StatefulWidget {
  final List<Map<String, dynamic>> targets;
  final VoidCallback onClose;
  final void Function(Map<String, dynamic> object, String type) onScanSuccess;

  const ScannerSim({
    super.key,
    required this.targets,
    required this.onClose,
    required this.onScanSuccess,
  });

  @override
  State<ScannerSim> createState() => _ScannerSimState();
}

class _ScannerSimState extends State<ScannerSim> {
  Map<String, dynamic>? selectedTarget;

  @override
  void initState() {
    super.initState();
    selectedTarget = widget.targets.isNotEmpty ? widget.targets[0] : null;
  }

  void handleSimulateScan() {
    if (selectedTarget == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Aucune cible à scanner disponible à proximité')),
      );
      return;
    }
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Scan Réussi'),
        content: Text(
            'Équipement détecté : ${selectedTarget!['type'].toUpperCase()} ${selectedTarget!['object']['code'] ?? selectedTarget!['object']['fid']}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Annuler'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              widget.onScanSuccess(selectedTarget!['object'], selectedTarget!['type']);
            },
            child: const Text('Ouvrir la fiche'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1a1a1a),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  '📷 Scanner QR Code / Code Équipement',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                TextButton(
                  onPressed: widget.onClose,
                  child: const Text(
                    'Fermer',
                    style: TextStyle(color: Color(0xFFe74c3c)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Expanded(
              flex: 2,
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.black,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Center(
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Container(
                        width: 180,
                        height: 180,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.white30),
                        ),
                        child: Stack(
                          children: [
                            Positioned(
                              top: 0,
                              left: 0,
                              child: Container(
                                width: 20,
                                height: 20,
                                decoration: const BoxDecoration(
                                  border: Border(
                                    top: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                    left: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                  ),
                                ),
                              ),
                            ),
                            Positioned(
                              top: 0,
                              right: 0,
                              child: Container(
                                width: 20,
                                height: 20,
                                decoration: const BoxDecoration(
                                  border: Border(
                                    top: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                    right: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                  ),
                                ),
                              ),
                            ),
                            Positioned(
                              bottom: 0,
                              left: 0,
                              child: Container(
                                width: 20,
                                height: 20,
                                decoration: const BoxDecoration(
                                  border: Border(
                                    bottom: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                    left: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                  ),
                                ),
                              ),
                            ),
                            Positioned(
                              bottom: 0,
                              right: 0,
                              child: Container(
                                width: 20,
                                height: 20,
                                decoration: const BoxDecoration(
                                  border: Border(
                                    bottom: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                    right: BorderSide(width: 4, color: Color(0xFF2ecc71)),
                                  ),
                                ),
                              ),
                            ),
                            const Positioned(
                              top: 0,
                              bottom: 0,
                              child: SizedBox(
                                width: double.infinity,
                                child: Divider(color: Color(0xFFe74c3c), thickness: 2),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const Text(
                        'Placer le code au centre du viseur',
                        style: TextStyle(color: Colors.white38, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 20),
            Expanded(
              flex: 1,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Équipements détectés par la caméra :',
                    style: TextStyle(color: Colors.white, fontSize: 13),
                  ),
                  const SizedBox(height: 10),
                  if (widget.targets.isNotEmpty)
                    SizedBox(
                      height: 110,
                      child: ListView.builder(
                        itemCount: widget.targets.length,
                        itemBuilder: (context, index) {
                          final tgt = widget.targets[index];
                          return GestureDetector(
                            onTap: () => setState(() => selectedTarget = tgt),
                            child: Container(
                              margin: const EdgeInsets.only(bottom: 6),
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: selectedTarget == tgt
                                    ? const Color(0xFF2ecc71)
                                    : const Color(0xFF2a2a2a),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                '${tgt['type'] == 'regard' ? '🕳️ Regard' : '🚰 Conduite'} : ${tgt['object']['code'] ?? tgt['object']['fid']}',
                                style: TextStyle(
                                  color: selectedTarget == tgt
                                      ? Colors.black
                                      : Colors.white70,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    )
                  else
                    const Text(
                      'Aucun équipement visible à proximité.',
                      style: TextStyle(
                        color: Colors.white38,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  const SizedBox(height: 15),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: selectedTarget != null ? handleSimulateScan : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: selectedTarget != null
                            ? const Color(0xFF2ecc71)
                            : Colors.grey[600],
                      ),
                      child: const Text(
                        '⚡ Simuler la détection QR',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }