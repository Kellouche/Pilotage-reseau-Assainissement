# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Centre d'aide : documentation Markdown rendue en HTML (extrait de api/main.py)
================================================================================
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from api.database import get_db

router = APIRouter()

_AIDE_DOCS_ROOT = Path("docs")


def _aide_doc_titre(chemin: Path) -> str:
    try:
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("# "):
                return ligne[2:].strip()
    except Exception:
        pass
    return chemin.stem


def _aide_docs_listing() -> list:
    """Liste des documents normatifs exposés dans le centre d'aide.

    Seuls les .md de premier niveau de docs/ et docs/adr/ sont exposés ;
    _archive_historique/ reste consultable dans le dépôt mais n'est pas
    servi (contenu non normatif).
    """
    items = []
    root = _AIDE_DOCS_ROOT
    if not root.is_dir():
        return items
    for p in sorted(root.glob("*.md")):
        items.append({"id": p.name, "titre": _aide_doc_titre(p), "groupe": "Documents de référence"})
    adr = root / "adr"
    if adr.is_dir():
        for p in sorted(adr.glob("*.md")):
            items.append({"id": f"adr/{p.name}", "titre": _aide_doc_titre(p), "groupe": "Architecture Decision Records"})
    return items


@router.get("/aide", response_class=HTMLResponse)
async def page_aide(request: Request, db=Depends(get_db)):
    """Centre d'aide : documentation produit/technique rendue pour les utilisateurs."""
    from api.main import _get_authenticated_user
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/aide", status_code=302)
    try:
        with open("templates/aide.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("""
        <h1>Erreur</h1>
        <p>Le centre d'aide n'est pas disponible.</p>
        <a href="/">Retour au cockpit</a>
        """, status_code=404)


@router.get("/aide/docs")
async def aide_docs_index(request: Request, db=Depends(get_db)):
    """Index JSON des documents exposés dans le centre d'aide."""
    from api.main import _get_authenticated_user
    user = _get_authenticated_user(request, db)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Non authentifié"})
    return {"documents": _aide_docs_listing()}


@router.get("/aide/doc/{doc_path:path}", response_class=HTMLResponse)
async def aide_doc_render(doc_path: str, request: Request, db=Depends(get_db)):
    """Rend un document Markdown normatif en fragment HTML.

    Whitelist stricte : uniquement docs/*.md et docs/adr/*.md.
    Les archives (_archive_historique/) et tout chemin traversant
    (..) sont refusés en stealth 404.
    """
    import re
    import markdown as _md

    from api.main import _get_authenticated_user
    user = _get_authenticated_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/aide", status_code=302)

    doc_path = doc_path.strip().lstrip("/")
    if not doc_path.lower().endswith(".md") or ".." in doc_path.split("/"):
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    root = _AIDE_DOCS_ROOT.resolve()
    cible = (root / doc_path).resolve()
    try:
        cible.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    if "_archive_historique" in cible.parts or not cible.is_file():
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    try:
        texte = cible.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    html = _md.markdown(
        texte,
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    )

    # Réécrit les liens relatifs *.md vers le routeur /aide/doc/ pour que la
    # navigation interne reste dans le centre d'aide (le HTML rendu contient
    # des href="...", plus la syntaxe Markdown d'origine).
    def _lien(m):
        cible_lien = m.group(1)
        if cible_lien.startswith(("http://", "https://", "/", "#", "mailto:")):
            return m.group(0)
        return f'href="/aide/doc/{cible_lien}{m.group(2) or ""}"'

    html = re.sub(r'href="([^"\s]+?\.md)(#[^"\s]*)?"', _lien, html)
    return HTMLResponse(
        f'<article class="aide-doc">{html}</article>',
        headers={"Cache-Control": "no-cache"},
    )


# ============================================================
# INCLUSION DES ROUTES
