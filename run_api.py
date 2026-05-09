#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lancement du serveur FastAPI pour la plateforme SWMM POC.
"""

import uvicorn
from config.settings import API_HOST, API_PORT, API_RELOAD

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=API_RELOAD,
        log_level="info"
    )
