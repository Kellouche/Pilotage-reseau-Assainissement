/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Recherche dans les couches du réseau et notifications utilisateur
 * ================================================================================
 */

/**
 * Recherche dans les couches du réseau
 * @param {string} terme - Terme de recherche
 */
function rechercherReseau(terme) {
    terme = terme.trim().toLowerCase();
    if (terme.length < 2) {
        alert('Veuillez entrer au moins 2 caractères pour rechercher.');
        return;
    }

    const matches = [];
    const coucheTypes = [
        { name: 'conduites', layer: conduitesLayer },
        { name: 'regards', layer: regardsLayer },
        { name: 'stations', layer: layers?.stationsLayer },
        { name: 'rejets', layer: layers?.rejectsLayer },
        { name: 'ouvrages', layer: layers?.ouvragesLayer },
        { name: 'step', layer: layers?.stepLayer }
    ];

    for (const { name, layer } of coucheTypes) {
        if (!layer) continue;
        layer.eachLayer(l => {
            const props = l.feature.properties || {};
            let found = false;
            for (const key in props) {
                const val = props[key];
                if (val !== null && val !== undefined) {
                    const strVal = String(val).toLowerCase();
                    if (strVal.includes(terme)) {
                        found = true;
                        break;
                    }
                }
            }
            if (found) {
                matches.push({ type: name, props, layer: l });
            }
        });
    }

    if (matches.length === 0) {
        alert('Aucun résultat trouvé.');
        return;
    }

    // Prendre le premier résultat pour le zoom et le popup
    const firstMatch = matches[0];
    const layer = firstMatch.layer;
    const props = firstMatch.props;

    // Calculer les bounds pour le zoom
    let bounds;
    if (layer instanceof L.LatLng) {
        bounds = L.latLngBounds(layer, layer);
    } else if (layer.getLatLng) {
        bounds = L.latLngBounds(layer.getLatLng(), layer.getLatLng());
    } else if (layer.getBounds) {
        bounds = layer.getBounds();
    } else {
        // Fallback: utiliser la première coordonnée disponible
        const latlng = layer.getLatLng ? layer.getLatLng() : L.latLng(0, 0);
        bounds = L.latLngBounds(latlng, latlng);
    }

    if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }

    // Créer un popup avec les propriétés
    let popupContent = `<div class="popup-content"><div class="popup-title">Résultat de recherche</div>`;
    for (const [k, v] of Object.entries(props)) {
        if (v !== null && v !== undefined) {
            popupContent += `<div class="popup-info"><strong>${k}:</strong> ${v}</div>`;
        }
    }
    popupContent += '</div>';

    // Lier le popup au layer et l'ouvrir
    layer.bindPopup(popupContent).openPopup();

    // Surligner temporairement le layer correspondant
    function highlightLayerTemporarily(l, delay = 2000) {
        let originalStyle;
        if (l instanceof L.Polyline) {
            originalStyle = l.options;
            l.setStyle({ color: '#ffff00', weight: 8, opacity: 0.8 });
        } else if (l instanceof L.CircleMarker) {
            originalStyle = {
                radius: l.options.radius,
                color: l.options.color,
                fillColor: l.options.fillColor,
                weight: l.options.weight
            };
            l.setStyle({ radius: 10, color: '#ffff00', fillColor: '#ffff00', weight: 2 });
        } else {
            // Pour les autres types de couches, on ne fait rien de spécial
            return;
        }
        setTimeout(() => {
            if (originalStyle) {
                l.setStyle(originalStyle);
            }
        }, delay);
    }

    highlightLayerTemporarily(layer, 3000);
}

function showNotification(msg, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${msg}`);

    let toast = document.getElementById('toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-notification';
        toast.className = 'notification';
        document.body.appendChild(toast);
    }

    toast.className = `notification notification-${type}`;
    toast.innerHTML = msg;
    toast.style.display = 'block';

    setTimeout(() => {
        toast.style.opacity = '1';
    }, 10);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.style.display = 'none';
        }, 300);
    }, 3000);
}
