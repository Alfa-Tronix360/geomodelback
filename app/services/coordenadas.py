"""Conversão de coordenadas geográficas WGS84 (latitude/longitude) para UTM.

Usa a série de Krüger (precisão milimétrica dentro do fuso). A zona UTM é escolhida
automaticamente pela longitude; o hemisfério sul usa o falso norte de 10 000 000 m.
Angola fica nos fusos 32S a 35S.
"""
from __future__ import annotations

import math
from typing import Any

_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996
_N = _F / (2 - _F)
_A_RECT = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALFA = (
    _N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16,
    13 * _N ** 2 / 48 - 3 * _N ** 3 / 5,
    61 * _N ** 3 / 240,
)
_C = 2 * math.sqrt(_N) / (1 + _N)


def zona_utm(longitude: float) -> int:
    return min(int((longitude + 180) // 6) + 1, 60)


def geo_para_utm(latitude: float, longitude: float) -> tuple[float, float, int, str]:
    """Devolve (x_este, y_norte, zona, hemisfério 'N'/'S')."""
    zona = zona_utm(longitude)
    meridiano = math.radians((zona - 1) * 6 - 180 + 3)
    fi = math.radians(latitude)
    dl = math.radians(longitude) - meridiano

    t = math.sinh(math.atanh(math.sin(fi)) - _C * math.atanh(_C * math.sin(fi)))
    xi = math.atan2(t, math.cos(dl))
    eta = math.atanh(math.sin(dl) / math.sqrt(1 + t * t))

    este = eta
    norte = xi
    for j, alfa in enumerate(_ALFA, start=1):
        este += alfa * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
        norte += alfa * math.sin(2 * j * xi) * math.cosh(2 * j * eta)

    x = 500000.0 + _K0 * _A_RECT * este
    y = _K0 * _A_RECT * norte
    hemisferio = "S" if latitude < 0 else "N"
    if hemisferio == "S":
        y += 10000000.0
    return round(x, 3), round(y, 3), zona, hemisferio


def completar_coordenadas(valores: dict[str, Any], forcar: bool = False) -> dict[str, Any]:
    """Preenche x/y (UTM) a partir da latitude/longitude quando faltam.

    Com ``forcar`` recalcula mesmo que x/y já existam (usado quando a lat/long muda).
    """
    lat, lon = valores.get("latitude"), valores.get("longitude")
    if lat is None or lon is None:
        return valores
    if forcar or valores.get("x") is None or valores.get("y") is None:
        valores["x"], valores["y"], _, _ = geo_para_utm(lat, lon)
    return valores
