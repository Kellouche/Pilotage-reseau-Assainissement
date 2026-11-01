# -*- coding: utf-8 -*-
"""
Configuration globale de la suite de tests pytest pour SWMM Platform SaaS.
Isole strictement la base de données de test pour ne JAMAIS impacter
la base opérationnelle locale de développement (swmm_platform.db).
"""
import os
import sys

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./test_swmm_platform.db"

