"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Script de vérification de l'état des routes de l'API REST
================================================================================
"""

import requests
import json

BASE_URL = "http://localhost:5002/api/v1"

def test_conduit_update():
    print("Testing conduit update with fid='C_0'...")
    # Get current to see if it exists
    # Actually just PATCH directly
    url = f"{BASE_URL}/network/conduites/C_0"
    data = {
        "diametre": 850,
        "materiau": "Béton"
    }
    try:
        res = requests.patch(url, json=data)
        if res.status_code == 200:
            print("✅ Conduit update succeeded!")
            print(res.json())
        else:
            print(f"❌ Conduit update failed with {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

def test_incident_create():
    print("Testing incident creation...")
    url = f"{BASE_URL}/terrain/incidents"
    data = {
        "type_incident": "Test Fuite",
        "gravite": "Haute",
        "statut": "Nouveau",
        "longitude": 1.2345,
        "latitude": 36.6789,
        "description": "Test via script"
    }
    try:
        res = requests.post(url, json=data)
        if res.status_code == 201:
            print("✅ Incident creation succeeded!")
            print(res.json())
        else:
            print(f"❌ Incident creation failed with {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import time
    time.sleep(2) # wait for server
    test_conduit_update()
    test_incident_create()
