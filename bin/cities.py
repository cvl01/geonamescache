#!/usr/bin/env python
"""Build cities{500,1000,5000,15000}.json from the GeoNames cities dumps.

The `alternatenames` column of the dumps is a flat, untagged mixture that also holds
GeoNames' own ASCII romanisation of every language a place has a name in, so Rotterdam
carried "Roterdam" and "Ratehrdam" as if they were forms anyone writes. Names are read
from alternateNamesV2.txt instead, the same way bin/admin1.py builds division names:
language-keyed, romanisations gone, and restricted to the languages of the city's own
country plus English.

All four dumps are built in one run, so the ~780 MB alternate names file is streamed
once for the union of their ids rather than once per dump.
"""
import csv
import json
import sys
from pathlib import Path

from _alternatenames import plain, read_alternate_names, read_country_languages

POPULATIONS = (500, 1000, 5000, 15000)

# cities dump column indices
COL_GEONAMEID = 0
COL_NAME = 1
COL_LATITUDE = 4
COL_LONGITUDE = 5
COL_FEATURECODE = 7
COL_COUNTRYCODE = 8
COL_ADMIN1CODE = 10
COL_ADMIN2CODE = 11
COL_POPULATION = 14
COL_TIMEZONE = 17

p_data = Path('datasets')
p_alternate = p_data.joinpath('alternateNamesV2.txt')
p_countryinfo = p_data.joinpath('countryInfo.txt')

p_cities = {population: p_data.joinpath(f'cities{population}.txt') for population in POPULATIONS}
for path in (*p_cities.values(), p_alternate, p_countryinfo):
    if not path.exists():
        sys.exit(f'{path} not found — run ./bin/download_data.py first')

datasets = {}
country_by_id = {}

for population, path in p_cities.items():
    cities = {}
    with path.open(encoding='utf-8') as fh:
        for record in csv.reader(fh, 'excel-tab'):
            geonameid = record[COL_GEONAMEID]

            # required because used as key
            if not geonameid:
                continue

            cities[geonameid] = {
                'geonameid': int(geonameid),
                'name': record[COL_NAME],
                'latitude': float(record[COL_LATITUDE]),
                'longitude': float(record[COL_LONGITUDE]),
                'countrycode': record[COL_COUNTRYCODE],
                'population': int(record[COL_POPULATION]),
                'timezone': record[COL_TIMEZONE],
                'admin1code': record[COL_ADMIN1CODE],
                'admin2code': record[COL_ADMIN2CODE],
                'featurecode': record[COL_FEATURECODE],
            }
            country_by_id[geonameid] = record[COL_COUNTRYCODE]
    datasets[population] = cities

languages_by_country = read_country_languages(p_countryinfo)
current, historic = read_alternate_names(p_alternate, country_by_id, languages_by_country)

for population, cities in datasets.items():
    for geonameid, city in cities.items():
        city['alternatenames'] = plain(current, geonameid)
        city['historicnames'] = plain(historic, geonameid)

    named = sum(1 for city in cities.values() if city['alternatenames'])
    p_data.joinpath(f'cities{population}.json').write_text(
        json.dumps(cities, ensure_ascii=False), encoding='utf-8'
    )
    print(f'cities{population}: {len(cities)} cities, {named} with alternate names')
