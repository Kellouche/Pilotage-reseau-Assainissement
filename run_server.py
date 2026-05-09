#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lancement du serveur FastAPI en production (sans auto-reload).
"""

import uvicorn
from config.settings import API_HOST, API_PORT

if __name__ == "__main__":
    print("=" * 60)
    print("Démarrage SWMM Platform POC - API Server")
    print(f"  URL: http://{API_HOST}:{API_PORT}")
    print(f"  Docs: http://{API_HOST}:{API_PORT}/docs")
    print("  Appuyez sur Ctrl+C pour arrêter")
    print("=" * 60)
    
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
        access_log=True
    )
