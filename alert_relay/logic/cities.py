# US cities with ~100k+ population (city name, state). Used for "major city" tornado matching.
_RAW = """
AL: Birmingham, Huntsville, Montgomery, Mobile, Tuscaloosa
AK: Anchorage
AZ: Phoenix, Tucson, Mesa, Chandler, Gilbert, Glendale, Scottsdale, Peoria, Tempe, Surprise, Goodyear, Buckeye, Yuma, San Tan Valley
AR: Little Rock, Fayetteville
CA: Los Angeles, San Diego, San Jose, San Francisco, Fresno, Sacramento, Long Beach, Oakland, Bakersfield, Anaheim, Stockton, Riverside, Irvine, Santa Ana, Chula Vista, Fremont, Santa Clarita, San Bernardino, Modesto, Fontana, Moreno Valley, Oxnard, Huntington Beach, Glendale, Ontario, Elk Grove, Rancho Cucamonga, Oceanside, Lancaster, Garden Grove, Palmdale, Salinas, Hayward, Corona, Sunnyvale, Pomona, Escondido, Roseville, Torrance, Fullerton, Visalia, Orange, Pasadena, Victorville, Santa Clara, Thousand Oaks, Simi Valley, Concord, Vallejo, Berkeley, Fairfield, Clovis, Carlsbad, Temecula, Murrieta, Antioch, Richmond, Ventura, Downey, Costa Mesa, El Monte, Inglewood, Jurupa Valley, West Covina, Santa Rosa, Norwalk, Burbank, Daly City, Rialto, El Cajon, San Mateo, Vista, Menifee, Hesperia, Indio, Chico, Santa Maria, Merced, Tracy, Redding, Compton, Livermore, Lake Forest, Whittier, Hemet, Santa Barbara, San Buenaventura
CO: Denver, Colorado Springs, Aurora, Fort Collins, Lakewood, Thornton, Arvada, Westminster, Pueblo, Greeley, Centennial, Boulder, Longmont, Loveland, Castle Rock
CT: Bridgeport, Stamford, New Haven, Hartford, Waterbury
DC: Washington
DE: Wilmington
FL: Jacksonville, Miami, Tampa, Orlando, St. Petersburg, Hialeah, Port St. Lucie, Cape Coral, Tallahassee, Fort Lauderdale, Pembroke Pines, Hollywood, Gainesville, Miramar, Coral Springs, Palm Bay, West Palm Beach, Clearwater, Lakeland, Pompano Beach, Spring Hill, Brandon, Riverview, Miami Gardens, Davie, Boca Raton, Sunrise, Plantation, Palm Coast, Deltona, Fort Myers, Kissimmee, Lehigh Acres, Largo, Melbourne, Palm Beach Gardens, Port Charlotte
GA: Atlanta, Columbus, Augusta, Macon, Savannah, Athens, South Fulton, Sandy Springs, Roswell
HI: Honolulu
ID: Boise, Meridian, Nampa
IL: Chicago, Aurora, Joliet, Naperville, Rockford, Springfield, Elgin, Peoria, Champaign
IN: Indianapolis, Fort Wayne, Evansville, South Bend, Carmel, Fishers
IA: Des Moines, Cedar Rapids, Davenport
KS: Wichita, Overland Park, Kansas City, Olathe, Topeka
KY: Louisville, Lexington
LA: New Orleans, Baton Rouge, Shreveport, Lafayette, Metairie, Lake Charles
ME: Portland
MD: Baltimore, Columbia, Germantown, Silver Spring
MA: Boston, Worcester, Springfield, Cambridge, Lowell, Brockton, New Bedford, Quincy, Lynn
MI: Detroit, Grand Rapids, Warren, Sterling Heights, Ann Arbor, Lansing, Dearborn, Livonia, Troy, Westland, Flint, Kalamazoo
MN: Minneapolis, St. Paul, Saint Paul, Rochester, Bloomington, Duluth
MS: Jackson, Gulfport
MO: Kansas City, St. Louis, Saint Louis, Springfield, Columbia, Independence, Lee's Summit, O'Fallon
MT: Billings, Missoula
NE: Omaha, Lincoln
NV: Las Vegas, Henderson, Reno, North Las Vegas, Paradise, Spring Valley, Enterprise, Sunrise Manor, Sparks
NH: Manchester
NJ: Newark, Jersey City, Paterson, Elizabeth, Lakewood, Edison, Woodbridge, Toms River, Hamilton, Trenton, Clifton, Camden
NM: Albuquerque, Las Cruces, Rio Rancho
NY: New York, Brooklyn, Queens, Bronx, Staten Island, Manhattan, Buffalo, Yonkers, Rochester, Syracuse, Albany, New Rochelle
NC: Charlotte, Raleigh, Greensboro, Durham, Winston-Salem, Fayetteville, Cary, Wilmington, High Point, Concord, Asheville, Greenville, Gastonia, Jacksonville
ND: Fargo, Bismarck
OH: Columbus, Cleveland, Cincinnati, Toledo, Akron, Dayton
OK: Oklahoma City, Tulsa, Norman, Broken Arrow, Edmond, Lawton, Moore
OR: Portland, Eugene, Salem, Gresham, Hillsboro, Bend, Beaverton, Medford
PA: Philadelphia, Pittsburgh, Allentown, Reading, Erie, Scranton
RI: Providence
SC: Charleston, Columbia, North Charleston, Mount Pleasant, Rock Hill, Greenville, Summerville
SD: Sioux Falls, Rapid City
TN: Nashville, Memphis, Knoxville, Chattanooga, Clarksville, Murfreesboro, Franklin, Jackson, Johnson City
TX: Houston, San Antonio, Dallas, Austin, Fort Worth, El Paso, Arlington, Corpus Christi, Plano, Lubbock, Laredo, Irving, Garland, Frisco, McKinney, Amarillo, Grand Prairie, Brownsville, Killeen, Denton, Pasadena, Mesquite, McAllen, Midland, Waco, Carrollton, Round Rock, Abilene, Pearland, Richardson, Odessa, Sugar Land, Beaumont, The Woodlands, College Station, Lewisville, League City, Tyler, Wichita Falls, Allen, San Angelo, Edinburg, Conroe, Bryan, Mission, New Braunfels, Atascocita, Longview, Pharr, Cypress, Spring, Baytown, Temple, Georgetown, Flower Mound, Leander, Kyle, Cedar Park, Harlingen, North Richland Hills, Mansfield, Missouri City, Pflugerville, Rowlett, Victoria, Port Arthur, Euless, DeSoto, Grapevine, Galveston, Bedford, Wylie, Little Elm, Celina, Prosper, Forney, Princeton
UT: Salt Lake City, West Valley City, West Jordan, Provo, Orem, St. George, Saint George, Ogden, Sandy, Lehi, South Jordan, Layton, Herriman, Millcreek, Taylorsville, Logan
VA: Virginia Beach, Chesapeake, Norfolk, Arlington, Richmond, Newport News, Alexandria, Hampton, Roanoke, Portsmouth, Suffolk
WA: Seattle, Spokane, Tacoma, Vancouver, Bellevue, Kent, Everett, Renton, Spokane Valley, Federal Way, Yakima, Kirkland, Auburn, Bellingham, Kennewick, Pasco, Marysville, Redmond, Sammamish, South Hill
WI: Milwaukee, Madison, Green Bay, Kenosha
WV: Charleston
PR: San Juan, Bayamon, Carolina, Ponce
"""
# Core counties of large metros: an areaDesc entry "County, ST" that names one of these counts as major-city.
_COUNTIES_RAW = """
AL: Jefferson, Madison, Montgomery, Mobile
AZ: Maricopa, Pima
AR: Pulaski
CA: Los Angeles, San Diego, Orange, Riverside, San Bernardino, Santa Clara, Alameda, Sacramento, Fresno, Kern, San Francisco
CO: Denver, Arapahoe, Adams, Jefferson, El Paso
DC: District of Columbia
FL: Miami-Dade, Broward, Palm Beach, Hillsborough, Orange, Duval, Pinellas
GA: Fulton, DeKalb, Cobb, Gwinnett, Chatham
IL: Cook, DuPage
IN: Marion
IA: Polk
KS: Sedgwick, Johnson, Wyandotte
KY: Jefferson, Fayette
LA: Orleans, East Baton Rouge, Jefferson, Caddo
MD: Baltimore City
MI: Wayne, Kent
MN: Hennepin, Ramsey
MO: Jackson, St. Louis City, St. Louis
NE: Douglas, Lancaster
NV: Clark, Washoe
NM: Bernalillo
NY: New York, Kings, Queens, Bronx, Richmond, Erie
NC: Mecklenburg, Wake, Guilford, Durham, Forsyth
OH: Franklin, Cuyahoga, Hamilton, Lucas, Montgomery, Summit
OK: Oklahoma, Tulsa, Cleveland
OR: Multnomah
PA: Philadelphia, Allegheny
SC: Charleston, Richland, Greenville
TN: Davidson, Shelby, Knox, Hamilton
TX: Harris, Dallas, Tarrant, Bexar, Travis, El Paso, Collin, Denton, Lubbock, Nueces
UT: Salt Lake
VA: Virginia Beach, Norfolk, Fairfax
WA: King, Pierce, Spokane, Snohomish
WI: Milwaukee, Dane
"""
def _parse(raw):
    out = []
    for line in raw.strip().splitlines():
        st, names = line.split(":", 1)
        for n in names.split(","):
            n = n.strip()
            if n:
                out.append((n, st.strip()))
    return out
CITIES = _parse(_RAW)
METRO_COUNTIES = _parse(_COUNTIES_RAW)
