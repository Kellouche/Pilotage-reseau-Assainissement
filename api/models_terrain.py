# -*- coding: utf-8 -*-
"""
Modèles pour les données collectées sur le terrain (Inspections et Incidents).
Référence canonique désormais intégrée dans api/models.py (Architecture Multi-Tenant SaaS).

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

from api.models import Inspection, Incident

__all__ = ["Inspection", "Incident"]
