from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Canalisation, Regard

router = APIRouter()


def _round_or_none(value, digits=2):
    return round(value, digits) if value is not None else None


def _observed_slope(conduite: Canalisation):
    if (
        conduite.prof_fe_am is None
        or conduite.prof_fe_av is None
        or conduite.longueur is None
        or conduite.longueur <= 0
    ):
        return None
    return (conduite.prof_fe_am - conduite.prof_fe_av) / conduite.longueur


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return None
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _representative_slope(db: Session, conduite: Canalisation):
    """
    Compute an observed representative slope from already documented conduites.
    Priority: same diameter/material/function, then same diameter, then global sample.
    """
    base_query = db.query(Canalisation).filter(
        Canalisation.id != conduite.id,
        Canalisation.longueur != None,
        Canalisation.longueur > 0,
        Canalisation.prof_fe_am != None,
        Canalisation.prof_fe_av != None,
    )

    query = base_query
    if conduite.diametre:
        query = query.filter(Canalisation.diametre == conduite.diametre)
    if conduite.materiau:
        query = query.filter(Canalisation.materiau == conduite.materiau)
    if conduite.fonction_mt:
        query = query.filter(Canalisation.fonction_mt == conduite.fonction_mt)

    candidates = query.limit(300).all()
    if len(candidates) < 5 and conduite.diametre:
        candidates = base_query.filter(Canalisation.diametre == conduite.diametre).limit(300).all()
    if len(candidates) < 5:
        candidates = base_query.limit(500).all()

    slopes = []
    for candidate in candidates:
        slope = _observed_slope(candidate)
        if slope is None:
            continue
        # Keep plausible gravity slopes only. This is not a fixed design slope.
        if 0 < slope <= 0.05:
            slopes.append(slope)

    return _median(slopes), len(slopes)


def _unavailable_suggestion(message, source_count=0, slope=None):
    return {
        "available": False,
        "confidence": "indisponible",
        "prof_fe_am": None,
        "prof_fe_av": None,
        "pente_pourcent": _round_or_none(slope * 100 if slope is not None else None, 3),
        "source_count": source_count,
        "message": message,
    }


@router.post("/manuel/{fid}")
def correction_manuelle(fid: str, data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Apply a manual correction to a conduite.
    """
    conduite = db.query(Canalisation).filter(Canalisation.fid == fid).first()
    if not conduite:
        raise HTTPException(status_code=404, detail="Conduite non trouvee")

    modifications = 0
    if "prof_fe_am" in data:
        conduite.prof_fe_am = data["prof_fe_am"]
        modifications += 1
    if "prof_fe_av" in data:
        conduite.prof_fe_av = data["prof_fe_av"]
        modifications += 1
    if "id_amont" in data:
        conduite.id_amont = data["id_amont"]
        modifications += 1
    if "id_aval" in data:
        conduite.id_aval = data["id_aval"]
        modifications += 1

    if modifications > 0:
        db.commit()
        return {"status": "success", "message": f"{modifications} champ(s) mis a jour pour {fid}"}
    return {"status": "info", "message": "Aucune modification apportee"}


@router.get("/hybride/suggestable_fids")
def suggestable_fids(db: Session = Depends(get_db)):
    """
    Returns a list of FIDs for Canalisation that have at least one valid boundary
    (amont or aval) from adjacent pipes, meaning they can potentially have a suggestion.
    This avoids making thousands of individual /suggest requests just to populate UI stars.
    """
    from sqlalchemy import text
    query = text("""
        SELECT DISTINCT c.fid
        FROM canalisation c
        LEFT JOIN canalisation c_amont ON c.id_amont = c_amont.id_aval AND c.id != c_amont.id
        LEFT JOIN canalisation c_aval ON c.id_aval = c_aval.id_amont AND c.id != c_aval.id
        WHERE c.longueur IS NOT NULL AND c.longueur > 0
          AND (c_amont.prof_fe_av IS NOT NULL OR c_aval.prof_fe_am IS NOT NULL)
    """)
    result = db.execute(query).fetchall()
    return {"suggestable_fids": [row[0] for row in result if row[0] is not None]}


@router.get("/hybride/suggest")
def suggestion_hybride(fid: str, anomalie_type: str, db: Session = Depends(get_db)):
    """
    Suggest a correction from adjacent conduites and slopes observed in similar data.
    The endpoint returns no green suggestion when the result is not defensible.
    """
    conduite = db.query(Canalisation).filter(Canalisation.fid == fid).first()
    if not conduite:
        raise HTTPException(status_code=404, detail="Conduite non trouvee")

    longueur = conduite.longueur
    prof_actuelle_am = conduite.prof_fe_am
    prof_actuelle_av = conduite.prof_fe_av

    conduite_amont = db.query(Canalisation).filter(
        Canalisation.id != conduite.id,
        Canalisation.id_aval == conduite.id_amont,
    ).first()
    conduite_aval = db.query(Canalisation).filter(
        Canalisation.id != conduite.id,
        Canalisation.id_amont == conduite.id_aval,
    ).first()

    boundary_am = (
        conduite_amont.prof_fe_av
        if conduite_amont and conduite_amont.prof_fe_av is not None
        else None
    )
    boundary_av = (
        conduite_aval.prof_fe_am
        if conduite_aval and conduite_aval.prof_fe_am is not None
        else None
    )
    representative_slope, source_count = _representative_slope(db, conduite)

    # Policy: only use representative_slope if at least MIN_SOURCES samples are available
    # Abaissé à 2 : avec seulement ~30% des canalisations ayant un profil complet,
    # il est irréaliste d'exiger 5 sources similaires pour toute suggestion.
    MIN_SOURCES = 2

    if longueur is None or longueur <= 0:
        suggestion = _unavailable_suggestion(
            "Aucune suggestion fiable disponible : longueur de conduite absente ou invalide.",
            source_count,
            representative_slope,
        )
    elif boundary_am is not None and boundary_av is not None:
        slope = (boundary_am - boundary_av) / longueur
        if 0 < slope <= 0.05:
            suggestion = {
                "available": True,
                "confidence": "fiable",
                "prof_fe_am": round(boundary_am, 2),
                "prof_fe_av": round(boundary_av, 2),
                "pente_pourcent": round(slope * 100, 3),
                "source_count": source_count,
                "message": "Suggestion calculee depuis les cotes connues des conduites adjacentes.",
            }
        else:
            suggestion = _unavailable_suggestion(
                "Aucune suggestion fiable disponible : les conduites adjacentes donnent une pente non plausible.",
                source_count,
                representative_slope,
            )
    elif representative_slope is not None and source_count >= MIN_SOURCES and boundary_am is not None:
        suggested_av = boundary_am - (longueur * representative_slope)
        suggestion = {
            "available": True,
            "confidence": "indicative",
            "prof_fe_am": round(boundary_am, 2),
            "prof_fe_av": round(suggested_av, 2),
            "pente_pourcent": round(representative_slope * 100, 3),
            "source_count": source_count,
            "message": "Suggestion indicative : cote amont adjacente connue et pente mediane observee sur des conduites similaires.",
        }
    elif representative_slope is not None and source_count >= MIN_SOURCES and boundary_av is not None:
        suggested_am = boundary_av + (longueur * representative_slope)
        suggestion = {
            "available": True,
            "confidence": "indicative",
            "prof_fe_am": round(suggested_am, 2),
            "prof_fe_av": round(boundary_av, 2),
            "pente_pourcent": round(representative_slope * 100, 3),
            "source_count": source_count,
            "message": "Suggestion indicative : cote aval adjacente connue et pente mediane observee sur des conduites similaires.",
        }
    else:
        # Not enough sources or no adjacent data
        if representative_slope is not None and source_count < MIN_SOURCES:
            suggestion = _unavailable_suggestion(
                f"Pente représentative insuffisante (sources={source_count} < {MIN_SOURCES}).", 
                source_count,
                representative_slope,
            )
        else:
            suggestion = _unavailable_suggestion(
                "Aucune suggestion fiable disponible : conduites adjacentes insuffisamment renseignees.",
                source_count,
                representative_slope,
            )

    # === Proposition hydraulique (fallback) ===
    # Si aucune suggestion trouvée ci-dessus, proposer une pente hydraulique basée sur vitesse cible
    try:
        if not suggestion.get('available'):
            diam = conduite.diametre
            # Heuristic: diam in mm if > 3
            diam_m = diam / 1000.0 if diam and diam > 3 else (diam if diam else None)
            longueur_val = longueur
            if diam_m and longueur_val and longueur_val > 0:
                # Manning formula for full flow: V = (1/n) * R^(2/3) * S^0.5 ; R = D/4 for circular full
                material = (conduite.materiau or '').lower()
                n = 0.013
                if 'pe' in material or 'pehd' in material:
                    n = 0.012
                if 'acier' in material or 'steel' in material:
                    n = 0.013
                # target velocity (m/s) - conservative self-cleaning threshold
                V_target = 0.6
                R = diam_m / 4.0
                # compute S required
                denom = (1.0 / n) * (R ** (2.0/3.0))
                if denom > 0:
                    S_req = (V_target / denom) ** 2
                    # convert to percent
                    pente_pct = round(S_req * 100, 4)
                    # compute delta elevation over length
                    delta = S_req * longueur_val
                    # build proposal
                    prof_am = conduite.prof_fe_am
                    prof_av = conduite.prof_fe_av
                    hyd_sugg = None
                    if prof_am is not None and (prof_av is None or prof_av == 0):
                        hyd_prof_av = round(prof_am - delta, 2)
                        hyd_sugg = { 'prof_fe_am': round(prof_am,2), 'prof_fe_av': hyd_prof_av }
                    elif prof_av is not None and (prof_am is None or prof_am == 0):
                        hyd_prof_am = round(prof_av + delta, 2)
                        hyd_sugg = { 'prof_fe_am': hyd_prof_am, 'prof_fe_av': round(prof_av,2) }
                    else:
                        # no absolute elevations -> suggest slope only
                        hyd_sugg = { 'prof_fe_am': None, 'prof_fe_av': None }

                    # accept hydraulic suggestion only if S_req is within hydraulically reasonable bounds
                    # Recommended bounds: between 0.05% and 5% (0.0005 - 0.05)
                    MIN_S_HYD = 0.0005
                    MAX_S_HYD = 0.05
                    print(f"[HYD] diam={diam}, diam_m={diam_m}, n={n}, R={R}, denom={denom}, S_req={S_req}, pente_pct={pente_pct}, delta={delta}")
                    # Diameter-based hydraulic bounds
                    # diam_m in meters
                    try:
                        if diam_m is not None:
                            if diam_m <= 0.3:
                                # petits diamètres 150-300 mm : pente recommandée 0.5% - 3%
                                min_S = 0.005  # 0.5%
                                max_S = 0.03   # 3%
                            else:
                                # gros diamètres >300 mm : pente recommandée 0.3% - 1%
                                min_S = 0.003  # 0.3%
                                max_S = 0.01   # 1%
                        else:
                            min_S = 0.003
                            max_S = 0.03

                        # absolute safety limits
                        ABS_MAX_S = 0.05  # 5%
                        ABS_MIN_S = 0.001  # 0.1% (safeguard)

                        # target velocity for auto-curage (choose conservative 0.6 m/s)
                        V_target = 0.6

                        # denom = (1/n) * R^(2/3)
                        denom = (1.0 / n) * (R ** (2.0/3.0))
                        if denom <= 0:
                            raise Exception('bad_denom')

                        S_req = (V_target / denom) ** 2

                        # Clamp S_req into hydraulically recommended range
                        final_S = S_req
                        capped = False

                        # Enforce absolute bounds
                        min_S = max(min_S, ABS_MIN_S)
                        max_S = min(max_S, ABS_MAX_S)

                        if S_req < min_S:
                            final_S = min_S
                            capped = True
                        elif S_req > max_S:
                            final_S = max_S
                            capped = True

                        # Ensure resulting velocity is not excessive; cap so V_final <= 3.0 m/s
                        V_final = denom * (final_S ** 0.5)
                        if V_final > 3.0:
                            # reduce final_S so V_final == 3.0
                            candidate_S = (3.0 / denom) ** 2
                            if candidate_S < max_S:
                                final_S = max(candidate_S, min_S)
                                capped = True

                        # Recompute values
                        pente_pct = round(final_S * 100, 4)
                        delta = final_S * longueur_val

                        if prof_am is not None and (prof_av is None or prof_av == 0):
                            hyd_prof_av = round(prof_am - delta, 2)
                            hyd_sugg = { 'prof_fe_am': round(prof_am,2), 'prof_fe_av': hyd_prof_av }
                        elif prof_av is not None and (prof_am is None or prof_am == 0):
                            hyd_prof_am = round(prof_av + delta, 2)
                            hyd_sugg = { 'prof_fe_am': hyd_prof_am, 'prof_fe_av': round(prof_av,2) }
                        else:
                            hyd_sugg = { 'prof_fe_am': None, 'prof_fe_av': None }

                        suggestion = {
                            'available': True,
                            'confidence': 'hydraulique_cappée' if capped else 'hydraulique',
                            'prof_fe_am': hyd_sugg['prof_fe_am'],
                            'prof_fe_av': hyd_sugg['prof_fe_av'],
                            'pente_pourcent': pente_pct,
                            'source_count': source_count,
                            's_req': S_req,
                            'final_S': final_S,
                            'V_target': V_target,
                            'V_final': denom * (final_S ** 0.5) if final_S else None,
                            'n_manning': n,
                            'capped': capped,
                            'message': f"Suggestion hydraulique basée sur V={V_target} m/s et Manning n={n} (S utilisée={round(final_S*100,4)}%).",
                        }
                    except Exception:
                        pass
    except Exception:
        pass

    return {
        "conduite_id": fid,
        "longueur": _round_or_none(longueur),
        "regard_amont": conduite.id_amont or "?",
        "regard_aval": conduite.id_aval or "?",
        "actuel": {
            "prof_fe_am": _round_or_none(prof_actuelle_am),
            "prof_fe_av": _round_or_none(prof_actuelle_av),
        },
        "suggestion": suggestion,
    }


@router.get("/profile/{fid}")
def profil_conduite(fid: str, db: Session = Depends(get_db)):
    """
    Retourne les détails d'une conduite et de ses regards pour l'affichage du profil.
    """
    print(f"[PROFILE] Request for fid={fid}")
    # Try robust lookup: exact, trimmed, numeric equivalence, LIKE
    conduite = db.query(Canalisation).filter(Canalisation.fid == fid).first()
    print(f"[PROFILE] initial query result: {bool(conduite)}")
    if not conduite:
        # try trimmed
        conduite = db.query(Canalisation).filter(Canalisation.fid == fid.strip()).first() if isinstance(fid, str) else None
    if not conduite and isinstance(fid, str) and fid.endswith('.0'):
        alt = fid[:-2]
        conduite = db.query(Canalisation).filter(Canalisation.fid == alt).first()
    if not conduite:
        # try numeric-match: if fid can be float, search string representation
        try:
            fnum = float(fid)
            conduite = db.query(Canalisation).filter(Canalisation.fid == str(fnum)).first()
        except Exception:
            pass
    if not conduite and isinstance(fid, str):
        # try case-insensitive like
        try:
            conduite = db.query(Canalisation).filter(Canalisation.fid.ilike(f"%{fid}%")).first()
        except Exception:
            pass

    # Last resort: if fid can be interpreted as integer, try matching Canalisation.id
    if not conduite:
        try:
            maybe_id = int(float(str(fid)))
            conduite = db.query(Canalisation).filter(Canalisation.id == maybe_id).first()
        except Exception:
            pass

    if conduite:
        regard_amont = db.query(Regard).filter(
            Regard.code == conduite.id_amont
        ).first() if conduite.id_amont else None

        regard_aval = db.query(Regard).filter(
            Regard.code == conduite.id_aval
        ).first() if conduite.id_aval else None

        return {
            "conduite_id": conduite.fid,
            "longueur": conduite.longueur,
            "diametre": conduite.diametre,
            "materiau": conduite.materiau,
            "forme_sect": conduite.forme_sect,
            "id_amont": conduite.id_amont or "?",
            "id_aval": conduite.id_aval or "?",
            "actuel": {
                "prof_fe_am": _round_or_none(conduite.prof_fe_am),
                "prof_fe_av": _round_or_none(conduite.prof_fe_av),
            },
            "regard_amont": {
                "code": regard_amont.code if regard_amont else None,
                "profondeur": regard_amont.profondeur if regard_amont else None,
                "latitude": regard_amont.latitude if regard_amont else None,
                "longitude": regard_amont.longitude if regard_amont else None,
            } if regard_amont else None,
            "regard_aval": {
                "code": regard_aval.code if regard_aval else None,
                "profondeur": regard_aval.profondeur if regard_aval else None,
                "latitude": regard_aval.latitude if regard_aval else None,
                "longitude": regard_aval.longitude if regard_aval else None,
            } if regard_aval else None,
        }

    # Fallback: essayer de lire la couche GeoPackage si la base de données ne contient pas la conduite
    try:
        import geopandas as gpd
        from pathlib import Path
        GPKG = Path(r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg")
        if GPKG.exists():
            layers = gpd.list_layers(GPKG)['name'].tolist()
            # trouver la couche canalisations
            couche_name = next((l for l in layers if 'canalis' in l.lower() or 'canali' in l.lower() or 'cana' in l.lower()), None)
            if couche_name:
                gdf = gpd.read_file(GPKG, layer=couche_name)
                # chercher la feature par différentes propriétés
                target_row = None
                for idx, row in gdf.iterrows():
                    props = {k.upper(): v for k, v in (row.items() if hasattr(row, 'items') else row._asdict().items())}
                    # check common keys
                    if any(str(props.get(k)) == str(fid) for k in ['FID', 'fid', 'ID', 'ID_AMONT', 'ID_AVAL', 'FID_COND', 'CODE']):
                        target_row = row
                        break
                if target_row is None:
                    # try by id_amont/id_aval
                    for idx, row in gdf.iterrows():
                        props = row
                        if any(str(v) == str(fid) for v in [props.get('ID_AMONT'), props.get('ID_AVAL'), props.get('ID_AMONT'.upper()), props.get('ID_AVAL'.upper())] if v is not None):
                            target_row = row
                            break

                if target_row is not None:
                    props = target_row
                    # normalize keys to lowercase access
                    def getp(k):
                        return props.get(k) if (k in props) else props.get(k.upper()) if (k.upper() in props) else None

                    prof_am = getp('PROF_FE_AM') or getp('PROF_FE_AM'.lower()) or getp('PROF_FE_AM'.upper()) or getp('PROF_FE_AM')
                    prof_av = getp('PROF_FE_AV') or getp('PROF_FE_AV'.lower()) or getp('PROF_FE_AV'.upper()) or getp('PROF_FE_AV')

                    id_am = getp('ID_AMONT') or getp('ID_AMONT'.lower())
                    id_av = getp('ID_AVAL') or getp('ID_AVAL'.lower())

                    # lire les regards si possible
                    regard_am = None
                    regard_av = None
                    # chercher couche regards
                    regard_layer_name = next((l for l in layers if 'regard' in l.lower()), None)
                    if regard_layer_name:
                        rgdf = gpd.read_file(GPKG, layer=regard_layer_name)
                        if id_am is not None:
                            rr = rgdf[(rgdf.apply(lambda r: str(r).find(str(id_am))>-1, axis=1))]
                            if len(rr) > 0:
                                rowr = rr.iloc[0]
                                regard_am = { 'code': id_am, 'profondeur': rowr.get('profondeur') if 'profondeur' in rowr else None, 'latitude': rowr.geometry.y if rowr.geometry is not None else None, 'longitude': rowr.geometry.x if rowr.geometry is not None else None }
                        if id_av is not None:
                            rr = rgdf[(rgdf.apply(lambda r: str(r).find(str(id_av))>-1, axis=1))]
                            if len(rr) > 0:
                                rowr = rr.iloc[0]
                                regard_av = { 'code': id_av, 'profondeur': rowr.get('profondeur') if 'profondeur' in rowr else None, 'latitude': rowr.geometry.y if rowr.geometry is not None else None, 'longitude': rowr.geometry.x if rowr.geometry is not None else None }

                    return {
                        'conduite_id': fid,
                        'longueur': getp('Longeur') or getp('LINEAIRE') or None,
                        'diametre': getp('DIAMETRE') or getp('Diametre') or None,
                        'materiau': getp('MATERIAU') or None,
                        'forme_sect': getp('FORMESECT') or None,
                        'id_amont': id_am or '?',
                        'id_aval': id_av or '?',
                        'actuel': { 'prof_fe_am': float(prof_am) if prof_am is not None else None, 'prof_fe_av': float(prof_av) if prof_av is not None else None },
                        'regard_amont': regard_am,
                        'regard_aval': regard_av
                    }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Conduite non trouvée")
def correction_automatique(db: Session = Depends(get_db)):
    """
    Batch repair for obvious topology issues. Kept conservative for the PoC.
    """
    conduites = db.query(Canalisation).filter(
        (Canalisation.id_amont == None) | (Canalisation.id_amont == "")
    ).limit(50).all()

    corrections_faites = 0
    for conduite in conduites:
        conduite.id_amont = "FIX_AUTO_AMONT"
        corrections_faites += 1

    db.commit()
    return {"status": "success", "message": f"{corrections_faites} conduites corrigees automatiquement."}
