"""OR/ID zone list for the Studio Active Alerts map (queue C, 2026-11-09).

Counties: OR counties bordering WA, ID counties bordering WA, and Oregon
coast counties (Lane and Douglas: coastal forecast zones only, not the
full inland county UGC). Forecast zones come from the NWS zone-county
correlation file (bp16ap26.dbx, effective 16 Apr 2026). Facebook posting
watchers are unchanged.
"""
# Oregon counties bordering Washington (west to east along the Columbia).
OR_BORDER = [
    ("ORC007", "Clatsop", "41007"),
    ("ORC009", "Columbia", "41009"),
    ("ORC051", "Multnomah", "41051"),
    ("ORC027", "Hood River", "41027"),
    ("ORC065", "Wasco", "41065"),
    ("ORC055", "Sherman", "41055"),
    ("ORC021", "Gilliam", "41021"),
    ("ORC049", "Morrow", "41049"),
    ("ORC059", "Umatilla", "41059"),
    ("ORC063", "Wallowa", "41063"),
]
# Oregon coast counties. Lane and Douglas are coastal-portion only (no ORC039 / ORC019).
OR_COAST = [
    ("ORC007", "Clatsop", "41007"),  # also a border county
    ("ORC057", "Tillamook", "41057"),
    ("ORC041", "Lincoln", "41041"),
    ("ORC011", "Coos", "41011"),
    ("ORC015", "Curry", "41015"),
]
# Idaho counties bordering Washington (north to south along the panhandle).
ID_BORDER = [
    ("IDC021", "Boundary", "16021"),
    ("IDC017", "Bonner", "16017"),
    ("IDC055", "Kootenai", "16055"),
    ("IDC009", "Benewah", "16009"),
    ("IDC057", "Latah", "16057"),
    ("IDC069", "Nez Perce", "16069"),
]

# Forecast zones from bp16ap26.dbx for the counties above, excluding inland
# Lane (ORZ118/125/128) and inland Douglas (ORZ023/025/027).
FORECAST_ZONES = [
    # PQR coast + coast range + lower Columbia / Portland / Gorge
    "ORZ101",  # Clatsop County Coast
    "ORZ102",  # Tillamook County Coast
    "ORZ103",  # Central Coast of Oregon (Lincoln, Lane coastal)
    "ORZ104",  # North Oregon Coast Range Lowlands
    "ORZ105",  # Central Oregon Coast Range Lowlands
    "ORZ106",  # North Oregon Coast Range
    "ORZ107",  # Central Oregon Coast Range
    "ORZ108",  # Lower Columbia River
    "ORZ109",  # Tualatin Valley (Multnomah)
    "ORZ110",  # West Hills and Chehalem Mountains
    "ORZ111",  # Inner Portland Metro
    "ORZ112",  # East Portland Metro
    "ORZ113",  # Outer Southeast Portland Metro
    "ORZ119",  # West Columbia River Gorge of Oregon above 500 ft
    "ORZ120",  # West Columbia River Gorge I-84 Corridor
    "ORZ121",  # Upper Hood River Valley
    "ORZ122",  # Central Columbia River Gorge I-84 Corridor
    "ORZ126",  # North Oregon Cascades
    # PDT border / gorge / basin / Blues / Wallowa
    "ORZ041",  # East Columbia River Gorge
    "ORZ044",  # Lower Columbia Basin of Oregon
    "ORZ050",  # Wallowa County
    "ORZ502",  # Northern Blue Mountains of Oregon
    "ORZ503",  # Southern Blue Mountains of Oregon
    "ORZ505",  # John Day Basin
    "ORZ507",  # Foothills of the Northern Blue Mountains of Oregon
    "ORZ508",  # Foothills of the Southern Blue Mountains of Oregon
    "ORZ509",  # East Slopes of the Oregon Cascades
    "ORZ510",  # North Central Oregon
    # MFR south coast (not inland Douglas ORZ023/025/027)
    "ORZ021",  # South Central Oregon Coast (Coos, Curry, Douglas coastal)
    "ORZ022",  # Curry County Coast
    "ORZ024",  # Eastern Curry County and Josephine County
    # Idaho panhandle / Palouse / Lewiston
    "IDZ001",  # Northern Panhandle
    "IDZ002",  # Coeur d'Alene Area
    "IDZ003",  # Idaho Palouse
    "IDZ004",  # Central Panhandle Mountains
    "IDZ026",  # Lewiston Area
    "IDZ027",  # Lewis and Southern Nez Perce Counties
]

# Oregon-coast marine not already in the WA pack (PZZ251/271 are already present).
MARINE_ZONES = [
    "PZZ210",  # Columbia River Bar
    "PZZ252",  # Cape Falcon to Cape Foulweather out 10 nm
    "PZZ253",  # Cape Foulweather to Florence out 10 nm
    "PZZ272",  # Cape Falcon to Cape Foulweather 10-60 nm
    "PZZ273",  # Cape Foulweather to Florence 10-60 nm
    "PZZ350",  # Florence to Cape Blanco out 10 nm
    "PZZ356",  # Florence to Cape Blanco 10-60 nm
    "PZZ370",  # Cape Blanco to Point St. George out 10 nm
    "PZZ376",  # Cape Blanco to Point St. George 10-60 nm
]

# Inland zones that must NOT be added (Lane/Douglas interior).
EXCLUDED_FORECAST = {"ORZ118", "ORZ125", "ORZ128", "ORZ023", "ORZ025", "ORZ027"}

# Few main towns for the new areas (collision layout still applies).
NEW_TOWNS = [
    {"n": "Portland", "lat": 45.5152, "lon": -122.6784, "pop": 652503, "notable": True, "tier": 0},
    {"n": "Astoria", "lat": 46.1879, "lon": -123.8313, "pop": 10181, "notable": True, "tier": 0},
    {"n": "Hood River", "lat": 45.7054, "lon": -121.5215, "pop": 8313, "notable": True, "tier": 0},
    {"n": "The Dalles", "lat": 45.5946, "lon": -121.1787, "pop": 16010, "notable": True, "tier": 0},
    {"n": "Pendleton", "lat": 45.6721, "lon": -118.7886, "pop": 17107, "notable": True, "tier": 0},
    {"n": "Tillamook", "lat": 45.4562, "lon": -123.8440, "pop": 5204, "notable": True, "tier": 1},
    {"n": "Lincoln City", "lat": 44.9582, "lon": -124.0179, "pop": 9815, "notable": True, "tier": 1},
    {"n": "Florence", "lat": 43.9826, "lon": -124.0998, "pop": 9396, "notable": True, "tier": 1},
    {"n": "Coos Bay", "lat": 43.3665, "lon": -124.2179, "pop": 15985, "notable": True, "tier": 0},
    {"n": "Brookings", "lat": 42.0526, "lon": -124.2839, "pop": 6744, "notable": True, "tier": 1},
    {"n": "Coeur d'Alene", "lat": 47.6777, "lon": -116.7805, "pop": 54628, "notable": True, "tier": 0},
    {"n": "Sandpoint", "lat": 48.2766, "lon": -116.5535, "pop": 9864, "notable": True, "tier": 0},
    {"n": "Moscow", "lat": 46.7324, "lon": -117.0002, "pop": 25435, "notable": True, "tier": 0},
    {"n": "Lewiston", "lat": 46.4165, "lon": -117.0177, "pop": 34203, "notable": True, "tier": 0},
]

MAIN_ORID = {"Portland", "Astoria", "Hood River", "The Dalles", "Pendleton",
             "Coos Bay", "Coeur d'Alene", "Sandpoint", "Moscow", "Lewiston"}
COASTAL_ORID = {"Astoria", "Tillamook", "Lincoln City", "Florence", "Coos Bay", "Brookings"}


def county_ids():
    seen, out = set(), []
    for row in OR_BORDER + OR_COAST + ID_BORDER:
        if row[0] not in seen:
            seen.add(row[0]); out.append(row)
    return out


def all_new_zone_ids():
    ids = [c[0] for c in county_ids()] + list(FORECAST_ZONES) + list(MARINE_ZONES)
    bad = set(ids) & EXCLUDED_FORECAST
    if bad:
        raise SystemExit("excluded zone slipped in: " + ",".join(sorted(bad)))
    return ids
