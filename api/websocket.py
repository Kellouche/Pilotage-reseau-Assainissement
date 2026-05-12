# Gestionnaire WebSocket pour synchronisation temps réel

from fastapi import WebSocket, WebSocketDisconnect
from typing import List


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        self.active_connections.append(websocket)
        print(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        """Diffuse un message à tous les clients WebSocket connectés."""
        print(f"Broadcasting to {len(self.active_connections)} clients: {message}")
        disconnected_clients = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
                print(f"Message sent to client: {message[:50]}...")
            except Exception as e:
                print(f"Error sending to client: {e}")
                disconnected_clients.append(connection)

        # Nettoyer les connexions défaillantes
        for client in disconnected_clients:
            try:
                self.disconnect(client)
            except ValueError:
                pass  # Client déjà déconnecté


manager = ConnectionManager()