#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lancement du serveur FastAPI pour la plateforme SWMM POC.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=5001,
        reload=True,  # auto-reload en dev
        log_level="info"
    )
