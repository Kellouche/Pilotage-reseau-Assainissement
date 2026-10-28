# -*- coding: utf-8 -*-
"""
Configuration globale de la suite de tests pytest pour SWMM Platform SaaS.
"""
import os
import sys

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./swmm_platform.db"
