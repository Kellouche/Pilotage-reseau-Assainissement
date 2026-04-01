"""Configuration pour le générateur SWMM."""

# Système de coordonnées
TARGET_CRS = 'EPSG:32631'  # UTM Zone 31N - Algérie

# Paramètres SWMM
SWMM_CONFIG = {
    'FLOW_UNITS': 'CMS',
    'INFILTRATION': 'HORTON',
    'FLOW_ROUTING': 'KINWAVE',
    'START_DATE': '01/01/2026',
    'START_TIME': '00:00:00',
    'REPORT_START_DATE': '01/01/2026',
    'REPORT_START_TIME': '00:00:00',
    'END_DATE': '01/02/2026',
    'END_TIME': '00:00:00',
    'ALLOW_PONDING': 'NO',
    'REPORT_STEP': '0:15:00',
    'WET_STEP': '0:05:00',
    'DRY_STEP': '1:00:00',
    'ROUTING_STEP': '0:30:00',
    'INERTIAL_DAMPING': 'PARTIAL',
    'NORMAL_FLOW_LIMITED': 'BOTH',
    'SKIP_STEADY_STATE': 'NO',
    'FORCE_MAIN_EQUATION': 'H-W',
}

# Paramètres par défaut pour les conduites
DEFAULT_ROUGHNESS = 0.013
DEFAULT_DEPTH_JUNCTION = 1.0

# Paramètres de distance pour l'appariement des nœuds
BUFFER_DISTANCE = 5.0  # mètres

# Mappage des formes de section
SHAPE_MAP = {
    'CIRCULAIRE': 'CIRCULAR',
    'RECTANGULAIRE': 'RECT_CLOSED',
    'OVOIDE': 'CIRCULAR',
}

# Paramètres pompe par défaut
DEFAULT_PUMP_CURVE = 'GENERIC_PUMP_CURVE'
GENERIC_PUMP_CURVE_POINTS = [
    (0.0, 0.0),
    (100.0, 10.0),
]
