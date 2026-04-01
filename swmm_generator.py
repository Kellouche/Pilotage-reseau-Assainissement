"""Générateur de fichiers SWMM .inp."""

import logging
import geopandas as gpd
from pathlib import Path
from typing import List, Optional, Dict
from config import SWMM_CONFIG, GENERIC_PUMP_CURVE_POINTS

logger = logging.getLogger(__name__)


class SWMMGenerator:
    """Génère les fichiers SWMM au format .inp."""

    def __init__(self):
        """Initialise le générateur."""
        self.output_lines = []

    def generate(
        self,
        nodes_gdf: gpd.GeoDataFrame,
        conduits: List[Dict],
        pumps: List[Dict],
        output_file: str = 'model.inp'
    ) -> str:
        """
        Génère le fichier SWMM complet.

        Args:
            nodes_gdf: GeoDataFrame avec tous les nœuds
            conduits: Liste des conduites
            pumps: Liste des pompes
            output_file: Nom du fichier de sortie

        Returns:
            Chemin du fichier généré
        """
        self.output_lines = []

        try:
            self._add_title()
            self._add_options()
            self._add_junctions(nodes_gdf)
            self._add_outfalls(nodes_gdf)
            self._add_storage()
            self._add_conduits(conduits)
            self._add_pumps(pumps)
            self._add_orifices()
            self._add_weirs()
            self._add_xsections(conduits)
            self._add_losses()
            self._add_inflows()
            self._add_dwf()
            self._add_curves(pumps)
            self._add_timeseries()
            self._add_report()
            self._add_tags()
            self._add_coordinates(nodes_gdf)
            self._add_map()

            # Écrire le fichier
            output_path = Path(output_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.output_lines))

            logger.info(f"Fichier SWMM généré: {output_file}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Erreur lors de la génération du fichier SWMM: {e}")
            raise

    def _add_title(self) -> None:
        """Ajoute la section [TITLE]."""
        self.output_lines.append('[TITLE]')
        self.output_lines.append(';; Projet du Réseau d\'Assainissement')
        self.output_lines.append('')

    def _add_options(self) -> None:
        """Ajoute la section [OPTIONS]."""
        self.output_lines.append('[OPTIONS]')
        self.output_lines.append(';;Option             Value')
        
        for key, value in SWMM_CONFIG.items():
            self.output_lines.append(f'{key:<19} {value}')
        
        self.output_lines.append('')

    def _add_junctions(self, nodes_gdf: gpd.GeoDataFrame) -> None:
        """Ajoute la section [JUNCTIONS]."""
        self.output_lines.append('[JUNCTIONS]')
        self.output_lines.append(';;Name           Elevation   MaxDepth   InitDepth   SurDepth   Aponded')
        
        junctions = nodes_gdf[nodes_gdf['node_type'] == 'JUNCTION']
        
        for idx, row in junctions.iterrows():
            line = (
                f"{row['swmm_id']:<15} {row['elevation']:>10.2f}   {1.0:>8.2f}   "
                f"{0.0:>8.2f}   {0.0:>7.2f}   {0.0:>7.2f}"
            )
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_outfalls(self, nodes_gdf: gpd.GeoDataFrame) -> None:
        """Ajoute la section [OUTFALLS]."""
        self.output_lines.append('[OUTFALLS]')
        self.output_lines.append(';;Name           Elevation   Type       StageData   Gated')
        
        outfalls = nodes_gdf[nodes_gdf['node_type'] == 'OUTFALL']
        
        for idx, row in outfalls.iterrows():
            line = (
                f"{row['swmm_id']:<15} {row['elevation']:>10.2f}     FREE       "
                f"{'0.0':>9}          NO"
            )
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_storage(self) -> None:
        """Ajoute la section [STORAGE]."""
        self.output_lines.append('[STORAGE]')
        self.output_lines.append(';;Name           Elevation   MaxDepth   InitDepth   Shape      CurveName   Aponded')
        self.output_lines.append('')

    def _add_conduits(self, conduits: List[Dict]) -> None:
        """Ajoute la section [CONDUITS]."""
        self.output_lines.append('[CONDUITS]')
        self.output_lines.append(
            ';;ID             From Node       To Node         Length      '
            'Roughness   InOffset   OutOffset   InitFlow   MaxFlow'
        )
        
        for conduit in conduits:
            line = (
                f"{conduit['conduit_id']:<15} {conduit['from_node']:<15} "
                f"{conduit['to_node']:<15} {conduit['length']:>10.2f}     "
                f"{conduit['roughness']:>8.3f}     {conduit['in_offset']:>8.2f}     "
                f"{conduit['out_offset']:>8.2f}     {conduit['init_flow']:>8.2f}     "
                f"{conduit['max_flow']:>7.2f}"
            )
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_pumps(self, pumps: List[Dict]) -> None:
        """Ajoute la section [PUMPS]."""
        self.output_lines.append('[PUMPS]')
        self.output_lines.append(
            ';;ID             From Node       To Node         PumpCurve       '
            'Status      Startup    Shutoff'
        )
        
        for pump in pumps:
            line = (
                f"{pump['pump_id']:<15} {pump['from_node']:<15} "
                f"{pump['to_node']:<15} {pump['pump_curve']:<15} STATUS       "
                f"OPEN       0.0"
            )
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_orifices(self) -> None:
        """Ajoute la section [ORIFICES]."""
        self.output_lines.append('[ORIFICES]')
        self.output_lines.append(';;ID             From Node       To Node         Type        Offset      Qcoeff     Gated')
        self.output_lines.append('')

    def _add_weirs(self) -> None:
        """Ajoute la section [WEIRS]."""
        self.output_lines.append('[WEIRS]')
        self.output_lines.append(';;ID             From Node       To Node         Type        CrestHt     Qcoeff     Gated')
        self.output_lines.append('')

    def _add_xsections(self, conduits: List[Dict]) -> None:
        """Ajoute la section [XSECTIONS]."""
        self.output_lines.append('[XSECTIONS]')
        self.output_lines.append(
            ';;Link           Shape           Geom1       Geom2       '
            'Geom3       Geom4       Barrels'
        )
        
        for conduit in conduits:
            line = (
                f"{conduit['conduit_id']:<15} {conduit['shape']:<15} "
                f"{conduit['geom1']:>10.2f}   {conduit['geom2']:>10.2f}   "
                f"{conduit['geom3']:>10.2f}   {conduit['geom4']:>10.2f}   "
                f"{conduit['barrels']:>7}"
            )
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_losses(self) -> None:
        """Ajoute la section [LOSSES]."""
        self.output_lines.append('[LOSSES]')
        self.output_lines.append(';;Link           InletLoss   OutletLoss   AvgLoss')
        self.output_lines.append('')

    def _add_inflows(self) -> None:
        """Ajoute la section [INFLOWS]."""
        self.output_lines.append('[INFLOWS]')
        self.output_lines.append(';;Node           Constituent   TimeSeries   Type   Mfactor   Sfactor   Baseline   Pattern')
        self.output_lines.append('')

    def _add_dwf(self) -> None:
        """Ajoute la section [DWF]."""
        self.output_lines.append('[DWF]')
        self.output_lines.append(';;Node           Constituent   Value   Pattern')
        self.output_lines.append('')

    def _add_curves(self, pumps: List[Dict]) -> None:
        """Ajoute la section [CURVES]."""
        self.output_lines.append('[CURVES]')
        self.output_lines.append(';;Name           Type          X-Value   Y-Value')
        
        if pumps:
            for x, y in GENERIC_PUMP_CURVE_POINTS:
                self.output_lines.append(f'GENERIC_PUMP_CURVE PUMP1         {x:>8.1f}     {y:>6.1f}')
        
        self.output_lines.append('')

    def _add_timeseries(self) -> None:
        """Ajoute la section [TIMESERIES]."""
        self.output_lines.append('[TIMESERIES]')
        self.output_lines.append(';;Name           Date          Time      Value')
        self.output_lines.append('')

    def _add_report(self) -> None:
        """Ajoute la section [REPORT]."""
        self.output_lines.append('[REPORT]')
        self.output_lines.append(';;Input          YES')
        self.output_lines.append(';;Continuity     YES')
        self.output_lines.append(';;Flow           YES')
        self.output_lines.append(';;Depth          YES')
        self.output_lines.append(';;Node           ALL')
        self.output_lines.append(';;Link           ALL')
        self.output_lines.append('')

    def _add_tags(self) -> None:
        """Ajoute la section [TAGS]."""
        self.output_lines.append('[TAGS]')
        self.output_lines.append(';;Object         ID            Tag')
        self.output_lines.append('')

    def _add_coordinates(self, nodes_gdf: gpd.GeoDataFrame) -> None:
        """Ajoute la section [COORDINATES]."""
        self.output_lines.append('[COORDINATES]')
        self.output_lines.append(';;Node           X-Coord          Y-Coord')
        
        for idx, row in nodes_gdf.iterrows():
            line = f"{row['swmm_id']:<15} {row['x']:>15.2f}   {row['y']:>15.2f}"
            self.output_lines.append(line)
        
        self.output_lines.append('')

    def _add_map(self) -> None:
        """Ajoute la section [MAP]."""
        self.output_lines.append('[MAP]')
        self.output_lines.append('DIMENSIONS       345019.85 4006157.97 355571.83 3998866.65')
        self.output_lines.append('UNITS            METERS')
        self.output_lines.append('')
