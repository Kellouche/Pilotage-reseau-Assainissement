"""
Configuration de l'application Celery pour SWMM Platform SaaS — Phase 2.3 (ADR-0003).

Gère la file de messages asynchrones (Redis / Celery) pour les simulations SWMM 5.2,
l'analyse topographique MNT, le calcul des clusters et l'ingestion de jeux de données SIG.
"""

import os
from celery import Celery

broker_url = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
result_backend = os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "redis://localhost:6379/1"))

# En mode test ou environnement léger sans Redis démarré, autoriser l'exécution synchrone
always_eager = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "False").lower() in ("1", "true", "yes")

celery_app = Celery(
    "swmm_platform_worker",
    broker=broker_url,
    backend=result_backend,
    include=[
        "workers.tasks.swmm_tasks",
        "workers.tasks.mnt_tasks",
    ],
)

celery_app.conf.update(
    task_always_eager=always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,       # 30 minutes max par simulation
    task_soft_time_limit=1500,  # 25 minutes avertissement soft
    worker_prefetch_multiplier=1,
)

if __name__ == "__main__":
    celery_app.start()
