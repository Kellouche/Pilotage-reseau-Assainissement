"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Contrôle d'intégrité de la structure SQLAlchemy ORM
================================================================================
"""

from api.database import SessionLocal
from api.models import Canalisation

db = SessionLocal()
try:
    # try to find by fid exact
    f='C_0'
    c = db.query(Canalisation).filter(Canalisation.fid==f).first()
    print('exact', bool(c))
    c2 = db.query(Canalisation).filter(Canalisation.fid.ilike('%C_0%')).first()
    print('ilike', bool(c2))
    # print some sample
    res = db.query(Canalisation).limit(5).all()
    for r in res:
        print('row fid', r.fid)
finally:
    db.close()
