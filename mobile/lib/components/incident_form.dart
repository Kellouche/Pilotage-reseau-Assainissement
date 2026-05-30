import 'package:flutter/material.dart';

class IncidentForm extends StatefulWidget {
  final Map<String, dynamic> coordinate;
  final VoidCallback onClose;
  final void Function(Map<String, dynamic>) onSave;

  const IncidentForm({
    super.key,
    required this.coordinate,
    required this.onClose,
    required this.onSave,
  });

  @override
  State<IncidentForm> createState() => _IncidentFormState();
}

class _IncidentFormState extends State<IncidentForm> {
  String typeIncident = 'Débordement';
  String gravite = 'Moyenne';
  String description = '';
  List<String> photos = [];

  void handleAddPhoto() {
    final mockPhotos = [
      'https://images.unsplash.com/photo-1541604193435-22419d562287?w=400',
      'https://images.unsplash.com/photo-1517649763962-0c623066013b?w=400',
    ];
    final randomPhoto = mockPhotos[DateTime.now().millisecond % mockPhotos.length];
    final newPhoto = '$randomPhoto&sig=${DateTime.now().millisecondsSinceEpoch}';
    setState(() => photos.add(newPhoto));
  }

  void handleSave() {
    if (description.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Veuillez saisir une description de l\'incident')),
      );
      return;
    }
    final incidentData = {
      'type_incident': typeIncident,
      'gravite': gravite,
      'description': description,
      'longitude': widget.coordinate['longitude'],
      'latitude': widget.coordinate['latitude'],
      'statut': 'À traiter',
      'photos': photos,
      'date_creation': DateTime.now().toIso8601String(),
    };
    widget.onSave(incidentData);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Incident signalé avec succès !')),
    );
  }

  Widget renderOption(String label, String current, List<String> options, ValueChanged<String> setter) {
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
                    selectedColor: const Color(0xFFc0392b),
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
            color: const Color(0xFFc0392b),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '🚨 Signaler un Incident',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Coordonnées : ${widget.coordinate['latitude'].toStringAsFixed(6)}, ${widget.coordinate['longitude'].toStringAsFixed(6)}',
                  style: const TextStyle(color: Color(0xFFfcdcd9), fontSize: 12),
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
                  renderOption(
                    'Type d\'incident',
                    typeIncident,
                    ['Débordement', 'Obstruction', 'Odeur suspecte', 'Effondrement', 'Autre'],
                    (v) => setState(() => typeIncident = v),
                  ),
                  renderOption(
                    'Niveau de gravité',
                    gravite,
                    ['Faible', 'Moyenne', 'Haute', 'Critique'],
                    (v) => setState(() => gravite = v),
                  ),
                  const Text('Description précise :', style: TextStyle(fontSize: 13)),
                  TextFormField(
                    maxLines: 3,
                    initialValue: description,
                    onChanged: (v) => description = v,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      hintText: 'Décrivez l\'anomalie ou l\'incident constaté sur place...',
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text('Photos de l\'incident (${photos.length})'),
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
                    backgroundColor: const Color(0xFFc0392b),
                  ),
                  child: const Text('Signaler'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }