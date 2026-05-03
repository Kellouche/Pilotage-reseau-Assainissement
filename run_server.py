#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lancement du serveur FastAPI en production (sans auto-reload).
"""

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("Démarrage SWMM Platform POC - API Server")
    print("  URL: http://localhost:5002")
    print("  Docs: http://localhost:5002/docs")
    print("  Appuyez sur Ctrl+C pour arrêter")
    print("=" * 60)
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=5002,  # Changé de 5001 à 5002
        reload=False,
        log_level="info",
        access_log=True
    )
