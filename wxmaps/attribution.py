"""Required credits. ECMWF wording follows the CC BY 4.0 open-data terms."""

from __future__ import annotations


def ecmwf_plate_credit() -> str:
    """One line on the image. CC BY 4.0 asks for credit, the licence, and a note of changes."""
    return "Source: ECMWF open data, CC BY 4.0. Modified."


def ecmwf_map_credit(year: int) -> str:
    """Full ECMWF notice. It travels with the page, not as a second block on the plate."""
    return (
        "Source: ECMWF open data, CC BY 4.0. "
        "Modified from ECMWF open data. "
        f"© {year} European Centre for Medium-Range Weather Forecasts (ECMWF). "
        "Source: www.ecmwf.int. "
        "This data is published under a Creative Commons Attribution 4.0 International "
        "(CC BY 4.0). https://creativecommons.org/licenses/by/4.0/ "
        "ECMWF does not accept any liability whatsoever for any error or omission in the data, "
        "their availability, or for any loss or damage arising from their use."
    )


def ecmwf_service_credit() -> str:
    return (
        "This product is based on data and products of the "
        "European Centre for Medium-Range Weather Forecasts (ECMWF)."
    )


def noaa_plate_credit() -> str:
    return "NOAA model data, public domain."


def noaa_map_credit() -> str:
    return (
        "NOAA model data, public domain. "
        "Basemap: U.S. Census Bureau TIGER/Line and Natural Earth, public domain."
    )


def footer_blocks(year: int) -> list[tuple[str, str]]:
    return [
        (
            "ECMWF",
            ecmwf_service_credit() + " " + ecmwf_map_credit(year),
        ),
        (
            "NOAA",
            "HRRR and GFS charts use NOAA model fields. Those United States government works are in the public domain.",
        ),
        (
            "Basemap",
            "Coast, state, and county lines are U.S. Census Bureau TIGER/Line cartographic boundaries and Natural Earth coastline, both public domain.",
        ),
        (
            "What was changed",
            "Charts are modified for display. Temperatures may be converted to °F, wind to mph, and precipitation to inches. "
            "Snowfall marked 10:1 is snow-water equivalent multiplied by ten. "
            "Absolute vorticity is plotted at 500 mb, computed from relative vorticity plus the Coriolis parameter when the file does not already contain it. "
            "HRRR wind barbs are rotated from grid-relative components to east and north.",
        ),
    ]


def footer_html(year: int) -> str:
    parts = []
    for title, text in footer_blocks(year):
        parts.append(f"<p><strong>{title}.</strong> {text}</p>")
    return "\n".join(parts)
