# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Lot A1+D0 — Test de Garde d'Isolation Multi-Tenant (§5.4)
Objet : Parcourt app.routes et échoue si une route hors allowlist n'a pas
        de dépendance tenant stricte.
================================================================================
"""

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Route
from api.main import app
from api.core.security import PUBLIC_ALLOWLIST, TENANT_ENFORCEMENT


# ---------------------------------------------------------------------------
# Surfaces connues en cours de migration (J2 - J7)
# Ce registre figé garantit que :
# 1. Aucune NOUVELLE route orpheline ne peut être ajoutée sans être bloquée par ce test.
# 2. Chaque route migrée sera retirée de cette liste jusqu'à atteindre 0 en J7/J8.
# ---------------------------------------------------------------------------
KNOWN_PENDING_SURFACES = {
    # Surfaces restantes à protéger (J6)
    ("GET", "/api/v1/layers"),
    ("GET", "/api/v1/simulations/pluviometrie/referentiel"),
    ("GET", "/api/v1/simulations/pluviometrie/stations"),
    ("GET", "/api/v1/simulations/scenarios"),
    ("GET", "/api/v1/simulations/typologies-sol"),
    ("GET", "/api/v1/terrain/incidents"),
    ("GET", "/api/v1/terrain/inspections"),
    ("GET", "/api/v1/terrain/inspections/{object_type}/{object_id}"),
    ("PATCH", "/api/v1/terrain/incidents/{incident_id}"),
    ("POST", "/api/v1/simulations/pluviometrie/bms-preview"),
    ("POST", "/api/v1/terrain/incidents"),
    ("POST", "/api/v1/terrain/inspections"),
    ("WS", "/api/v1/jobs/ws/{job_id}"),
}


def _get_recursive_calls(dependant):
    calls = []
    if not dependant:
        return calls
    if dependant.call:
        calls.append(dependant.call)
    for sub in dependant.dependencies:
        calls.extend(_get_recursive_calls(sub))
    return calls


def _extract_all_routes(app_or_router, prefix=""):
    all_routes = []
    routes = getattr(app_or_router, "routes", [])
    for r in routes:
        r_type = type(r).__name__
        if r_type == "_IncludedRouter":
            pfx = prefix + getattr(r.include_context, "prefix", "")
            router_deps = getattr(r.include_context, "dependencies", [])
            for sub_r in getattr(r.original_router, "routes", []):
                all_routes.append((sub_r, pfx, router_deps))
        elif isinstance(r, (APIRoute, APIWebSocketRoute, Route)):
            all_routes.append((r, prefix, []))
        elif hasattr(r, "routes"):
            all_routes.extend(_extract_all_routes(r, prefix))
    return all_routes


def _has_strict_tenant_dependency(calls):
    dep_names = [getattr(c, "__name__", str(c)) for c in calls]
    # Seules ces dépendances garantissent la résolution obligatoire du tenant
    # (get_tenant_context_optional ne compte PAS car il accepte l'anonymat)
    return any(
        name in (
            "get_tenant_context",
            "require_role",
            "require_superadmin",
            "require_network_access",
        )
        or "tenant" in name.lower() and "optional" not in name.lower()
        for name in dep_names
    )


def test_public_allowlist_consistency():
    """Toutes les routes déclarées dans PUBLIC_ALLOWLIST doivent exister dans l'application."""
    all_routes = _extract_all_routes(app)
    existing_surfaces = set()
    for r, pfx, _ in all_routes:
        full_path = pfx + r.path if pfx and not r.path.startswith(pfx) else r.path
        if pfx and not full_path.startswith(pfx):
            full_path = pfx + full_path
        if isinstance(r, APIWebSocketRoute):
            methods = ["WS"]
        else:
            methods = list(r.methods - {"HEAD", "OPTIONS"})
        for m in methods:
            existing_surfaces.add((m, full_path))

    for m, p in PUBLIC_ALLOWLIST:
        assert (m, p) in existing_surfaces, (
            f"Route de l'allowlist publique inexistante sur l'application : {m} {p}"
        )


def test_no_unlisted_unprotected_routes():
    """
    GARDE-FOU MULTI-TENANT PRINCIPAL (§5.4) :
    Aucune route hors PUBLIC_ALLOWLIST et hors KNOWN_PENDING_SURFACES ne doit
    répondre sans dépendance tenant stricte.
    """
    all_routes = _extract_all_routes(app)
    violations = []

    for r, pfx, r_deps in all_routes:
        full_path = pfx + r.path if pfx and not r.path.startswith(pfx) else r.path
        if pfx and not full_path.startswith(pfx):
            full_path = pfx + full_path

        if isinstance(r, APIWebSocketRoute):
            methods = ["WS"]
        else:
            methods = list(r.methods - {"HEAD", "OPTIONS"})

        all_calls = _get_recursive_calls(getattr(r, "dependant", None))
        for rd in r_deps:
            if hasattr(rd, "dependant"):
                all_calls.extend(_get_recursive_calls(rd.dependant))
            elif callable(rd):
                all_calls.append(rd)

        is_protected = _has_strict_tenant_dependency(all_calls)

        for m in methods:
            surface = (m, full_path)
            if surface in PUBLIC_ALLOWLIST:
                continue
            if is_protected:
                continue
            if surface in KNOWN_PENDING_SURFACES:
                continue

            violations.append(f"{m} {full_path}")

    assert not violations, (
        f"VIOLATION GARDE-FOU TENANT : {len(violations)} route(s) non autorisée(s) et non protégée(s) détectée(s) :\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_pending_surfaces_count_ceiling():
    """Le nombre de surfaces en attente ne doit jamais dépasser le plafond (13 après J5)."""
    assert len(KNOWN_PENDING_SURFACES) <= 13


def test_tenant_enforcement_fail_closed_mode():
    """Le mode TENANT_ENFORCEMENT doit être strict ou audit (fail-closed)."""
    assert TENANT_ENFORCEMENT in ("strict", "audit")
