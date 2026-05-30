import 'package:flutter/material.dart';

class FicheTerrain extends StatefulWidget {
  final Map<String, dynamic> object;
  final String type;
  final VoidCallback onClose;
  final void Function(Map<String, dynamic>) onSave;

  const FicheTerrain({
    super.key,
    required this.object,
    required this.type,
    required this.onClose,
    required this.onSave,
  });

  @override
  State<FicheTerrain> createState() => _FicheTerrainState();
}

class _FicheTerrainState extends State<FicheTerrain> {
  String etat = 'Bon';
  String niveauEau = 'Normal';
  String obstruction = 'Aucune';
  String odeur = 'Aucune';
  bool debordement = false;
  String commentaires = '';
  List<String> photos = [];
  String statut = 'À vérifier';

  void handleAddPhoto() {
    final mockPhotos = [
      'https://images.unsplash.com/photo-1542060748-10c28b629f6f?w=400',
      'https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=400',
      'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=400',
    ];
    final randomPhoto = mockPhotos[DateTime.now().millisecond % mockPhotos.length];
    final newPhoto = '$randomPhoto&sig=${DateTime.now().millisecondsSinceEpoch}';
    setState(() => photos.add(newPhoto));
  }

  void handleSave() {
    final inspectionData = {
      'object_type': widget.type,
      'object_id': widget.object['code'] ?? widget.object['fid'] ?? widget.object['id']?.toString(),
      'etat': etat,
      'niveau_eau': niveauEau,
      'obstruction': obstruction,
      'odeur': odeur,
      'debordement': debordement,
      'commentaires': commentaires,
      'photos': photos,
      'statut': statut,
      'date_inspection': DateTime.now().toIso8601String(),
    };
    widget.onSave(inspectionData);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Inspection enregistrée avec succès !')),
    );
  }

  Widget renderDropdown(String label, String current, List<String> options, ValueChanged<String> setter) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 4),
        Wrap(
          spacing: 6,
          children: options
              .map((opt) => ChoiceChip(
                    label: Text(opt),
                    selected: current == opt,
                    onSelected: (selected) {
                      if (selected) setter(opt);
                    },
                    selectedColor: const Color(0xFF16213e),
                    labelStyle: TextStyle(
                      color: current == opt ? Colors.white : Colors.black,
                    ),
                  ))
              .toList(),
        ),
        const SizedBox(height: 12),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: const Color(0xFF16213e),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Fiche Terrain - ${widget.type.toUpperCase()}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'ID : ${widget.object['code'] ?? widget.object['fid'] ?? widget.object['id']}',
                  style: const TextStyle(color: Colors.white70),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Fiche Technique',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (widget.object['diametre'] != null)
                    Text('• Diamètre : ${widget.object['diametre']} mm'),
                  if (widget.object['longueur'] != null)
                    Text('• Longueur : ${widget.object['longueur']} m'),
                  if (widget.object['materiau'] != null)
                    Text('• Matériau : ${widget.object['materiau']}'),
                  if (widget.object['profondeur'] != null)
                    Text('• Profondeur : ${widget.object['profondeur']} m'),
                  if (widget.object['commune'] != null)
                    Text('• Commune : ${widget.object['commune']}'),
                  if (widget.object['nom_voie'] != null)
                    Text('• Voie : ${widget.object['nom_voie']}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Observations terrain',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  renderDropdown('État général', etat, ['Bon', 'Moyen', 'Mauvais'], (v) => setState(() => etat = v)),
                  renderDropdown('Niveau d\'eau', niveauEau, ['Vide', 'Normal', 'Sous charge', 'Débordement'], (v) => setState(() => niveauEau = v)),
                  renderDropdown('Obstruction', obstruction, ['Aucune', 'Partielle', 'Totale'], (v) => setState(() => obstruction = v)),
                  renderDropdown('Odeur', odeur, ['Aucune', 'Légère', 'Forte'], (v) => setState(() => odeur = v)),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Débordement actif :', style: TextStyle(fontSize: 13)),
                      Switch(
                        value: debordement,
                        onChanged: (v) => setState(() => debordement = v),
                        activeColor: const Color(0xFFe74c3c),
                      ),
                    ],
                  ),
                  renderDropdown('Statut de validation', statut, ['À vérifier', 'Corrigé terrain', 'Validé bureau'], (v) => setState(() => statut = v)),
                  const SizedBox(height: 8),
                  const Text('Commentaires / Diagnostic :', style: TextStyle(fontSize: 13)),
                  TextFormField(
                    maxLines: 3,
                    initialValue: commentaires,
                    onChanged: (v) => commentaires = v,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      hintText: 'Renseigner les constatations terrain...',
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text('Photos d\'inspection (${photos.length})'),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      ...photos.map((uri) => Image.network(
                            uri,
                            width: 50,
                            height: 50,
                            fit: BoxFit.cover,
                          )),
                      GestureDetector(
                        onTap: handleAddPhoto,
                        child: Container(
                          width: 50,
                          height: 50,
                          decoration: BoxDecoration(
                            border: Border.all(style: BorderStyle.solid),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Center(child: Text('📸 +')),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: widget.onClose,
                  child: const Text('Annuler'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: handleSave,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF27ae60),
                  ),
                  child: const Text('Enregistrer'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }