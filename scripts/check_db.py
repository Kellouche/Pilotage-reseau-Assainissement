import sqlite3
import requests

DB = 'D:/IA Water Data Analysis/Assainissement/swmm-platform-poc/swmm_platform.db'
conn = sqlite3.connect(DB)
c = conn.cursor()
try:
    c.execute("SELECT fid, id, prof_fe_am, prof_fe_av, longueur FROM conduites WHERE fid IS NOT NULL LIMIT 10")
    rows = c.fetchall()
    print('found', len(rows))
    for r in rows:
        print('FID:', r[0],'id:',r[1],'prof_am:',r[2],'prof_av:',r[3],'longueur:',r[4])
    if rows:
        fid = rows[0][0]
        print('\nQuerying API profile for fid=', fid)
        resp = requests.get(f'http://127.0.0.1:5001/api/v1/corrections/profile/{fid}', timeout=10)
        print('STATUS', resp.status_code)
        print(resp.json())
except Exception as e:
    print('ERR', e)
finally:
    conn.close()
