"""Serviços de geometria e cálculos geológicos do MVP."""
from __future__ import annotations

import math

from fastapi import HTTPException

from app.models import DrillHole, DrillSurvey
from app.schemas import PontoTrajectoria, TrajectoriaSaida

TIPOS_GEOJSON = {
    "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon",
    "GeometryCollection", "Feature", "FeatureCollection",
}


def validar_geojson(geometria: dict | None) -> None:
    if geometria is None:
        return
    if not isinstance(geometria, dict) or geometria.get("type") not in TIPOS_GEOJSON:
        raise HTTPException(422, "Geometria inválida: indique um objecto GeoJSON com 'type' válido")
    if geometria.get("type") not in ("GeometryCollection", "Feature", "FeatureCollection") \
            and "coordinates" not in geometria:
        raise HTTPException(422, "Geometria inválida: falta 'coordinates'")


def _passo(x: float, y: float, z: float, comprimento: float, azimute: float, inclinacao: float):
    """Avança num segmento recto. Azimute em graus a partir do Norte; inclinação negativa para baixo."""
    inc = math.radians(inclinacao)
    az = math.radians(azimute)
    return (
        x + comprimento * math.cos(inc) * math.sin(az),
        y + comprimento * math.cos(inc) * math.cos(az),
        z + comprimento * math.sin(inc),
    )


def trajectoria(furo: DrillHole, surveys: list[DrillSurvey]) -> TrajectoriaSaida:
    """Trajectória 3D simplificada (tangente) a partir do collar e dos surveys.

    Convenção: x = Este, y = Norte, z = cota; azimute 0–360°; inclinação -90° (vertical para baixo)
    a +90°. Cada survey orienta o segmento até à profundidade seguinte.
    """
    if furo.x is None or furo.y is None or furo.z is None:
        raise HTTPException(409, "O furo não tem coordenadas x/y/z para calcular a trajectória")
    collar = PontoTrajectoria(profundidade=0.0, x=furo.x, y=furo.y, z=furo.z)
    if not surveys:
        return TrajectoriaSaida(drill_hole_id=furo.id, collar=collar, comprimento=0.0, pontos=[collar])

    ordenados = sorted(surveys, key=lambda s: s.profundidade)
    pontos = [collar]
    x, y, z = furo.x, furo.y, furo.z
    anterior = 0.0
    for survey in ordenados:
        delta = survey.profundidade - anterior
        if delta < 0:
            continue
        if delta > 0:
            x, y, z = _passo(x, y, z, delta, survey.azimute, survey.inclinacao)
        pontos.append(PontoTrajectoria(profundidade=survey.profundidade, x=round(x, 4), y=round(y, 4), z=round(z, 4)))
        anterior = survey.profundidade
    return TrajectoriaSaida(drill_hole_id=furo.id, collar=collar, comprimento=anterior, pontos=pontos)


def calcular_estimativa(
    volume_m3: float | None, densidade: float | None, teor_corte: float | None, unidade_teor: str,
) -> tuple[float | None, float | None]:
    """Tonnagem = volume × densidade; metal contido = tonelagem × teor (convertido para fracção)."""
    tonelagem = volume_m3 * densidade if volume_m3 is not None and densidade is not None else None
    metal = None
    if tonelagem is not None and teor_corte is not None:
        unidade = unidade_teor.strip().lower()
        if unidade == "%":
            metal = tonelagem * teor_corte / 100
        elif unidade in ("ppm", "g/t", "gt"):
            metal = tonelagem * teor_corte / 1_000_000
        elif unidade == "ppb":
            metal = tonelagem * teor_corte / 1_000_000_000
        else:
            metal = tonelagem * teor_corte
    return tonelagem, metal
