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
