import asyncio
import websockets
import requests
import json
import threading
import time

API_URL = "http://localhost:5002/api/v1/terrain/incidents"
WS_URL = "ws://localhost:5002/ws/sync"

def trigger_incident():
    time.sleep(2)  # wait for WS to connect
    data = {
        "type_incident": "Fuite",
        "gravite": "Haute",
        "statut": "Nouveau",
        "longitude": 1.2345,
        "latitude": 36.6789,
        "description": "Test via script"
    }
    print("Envoi requête POST pour incident...")
    res = requests.post(API_URL, json=data)
    print("Réponse:", res.status_code, res.text)

async def listen_ws():
    print(f"Connexion à {WS_URL}...")
    try:
        async with websockets.connect(WS_URL, origin="http://localhost:5002") as ws:
            print("WebSocket connecté.")
            
            # Start the thread to trigger the incident
            t = threading.Thread(target=trigger_incident)
            t.start()
            
            while True:
                msg = await ws.recv()
                print(f"Reçu depuis WS : {msg}")
                if "Incident signalé" in msg:
                    print("Test WebSocket RÉUSSI.")
                    break
    except Exception as e:
        print(f"Erreur WS: {e}")

if __name__ == "__main__":
    asyncio.run(listen_ws())
