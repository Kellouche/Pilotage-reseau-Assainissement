/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Édition interactive des attributs des regards et conduites
 * ================================================================================
 */

(() => {
    const state = window.mapState;
    let currentEditProperties = null;
    let currentEditType = null;
    let currentEditId = null;

    function initEditAttributes() {
        window.editConduit = (index) => {
            openEditModal(state.conduitProperties[index], 'conduite');
        };

        window.editRegard = (index) => {
            openEditModal(state.regardProperties[index], 'regards');
        };

        document.getElementById('cancel-btn').addEventListener('click', () => {
            document.getElementById('edit-modal').style.display = 'none';
        });

        document.getElementById('close-btn-header').addEventListener('click', () => {
            document.getElementById('edit-modal').style.display = 'none';
        });

        document.getElementById('save-btn').addEventListener('click', saveEdit);

        // Logique de glisser-déposer (Drag & Drop) pour la modale
        const editModal = document.getElementById('edit-modal');
        const modalHeader = document.getElementById('modal-header');
        let isDragging = false;
        let offsetX, offsetY;

        if (modalHeader) {
            modalHeader.addEventListener('mousedown', (e) => {
                isDragging = true;
                offsetX = e.clientX - editModal.getBoundingClientRect().left;
                offsetY = e.clientY - editModal.getBoundingClientRect().top;
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
            });
        }

        function onMouseMove(e) {
            if (!isDragging) return;
            editModal.style.left = (e.clientX - offsetX) + 'px';
            editModal.style.top = (e.clientY - offsetY) + 'px';
        }

        function onMouseUp() {
            isDragging = false;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }
    }

    function openEditModal(properties, type) {
        currentEditProperties = properties;
        currentEditType = type;
        currentEditId = properties.conduit_id || properties.fid || properties.code || properties.Code || properties.id;

        const title = type === 'conduite' ? 'Modifier Conduite' : `Modifier ${type.charAt(0).toUpperCase() + type.slice(1)}`;
        document.getElementById('modal-title').textContent = title;

        const form = document.getElementById('edit-form');
        form.innerHTML = '';

        if (type === 'conduite') {
            addField(form, 'longueur', 'Longueur (m)', properties.longueur || properties.LONGUEUR || '');
            addField(form, 'diametre', 'Diamètre (mm)', properties.diametre || properties.DIAMETRE || '');
            addField(form, 'materiau', 'Matériau', properties.materiau || properties.MATERIAU || '');
            addField(form, 'nom_voie', 'Nom', properties.nom_voie || properties.NOM || properties.f_nom || '');
        } else if (type === 'regards') {
            addField(form, 'code', 'Code', properties.code || '');
            addField(form, 'type_regard', 'Type', properties.type_regard || '');
            addField(form, 'diametre', 'Diamètre', properties.diametre || '');
            addField(form, 'profondeur', 'Profondeur', properties.profondeur || '');
        } else {
            addField(form, 'nom', 'Nom', properties.nom || '');
            addField(form, 'type', 'Type', properties.type || '');
        }

        document.getElementById('edit-modal').style.display = 'flex';
    }

    function addField(form, name, label, value) {
        const div = document.createElement('div');
        div.style.marginBottom = '10px';
        div.innerHTML = `
            <label style="display: block; margin-bottom: 5px;">${label}:</label>
            <input type="text" name="${name}" value="${escapeHtml(value)}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
        `;
        form.appendChild(div);
    }

    async function saveEdit() {
        const formData = new FormData(document.getElementById('edit-form'));
        const updateData = {};

        for (let [key, value] of formData.entries()) {
            if (value.trim()) {
                if (['longueur', 'diametre', 'profondeur'].includes(key)) {
                    updateData[key] = parseFloat(value);
                } else {
                    updateData[key] = value;
                }
            }
        }

        const endpoint = currentEditType === 'conduite'
            ? `/api/v1/network/conduites/${currentEditId}`
            : `/api/v1/network/regards/${currentEditId}`;

        try {
            const response = await fetch(endpoint, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });

            if (response.ok) {
                alert('Modifications enregistrées');
                document.getElementById('edit-modal').style.display = 'none';
                location.reload();
            } else {
                alert('Erreur lors de la sauvegarde');
            }
        } catch (error) {
            console.error('Erreur:', error);
            alert('Erreur réseau');
        }
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&')
            .replace(/</g, '<')
            .replace(/>/g, '>')
            .replace(/"/g, '"')
            .replace(/'/g, '&#039;');
    }

    window.initEditAttributes = initEditAttributes;
    window.openEditModal = openEditModal;
})();
