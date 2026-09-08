#!/usr/bin/env python
import csv
import json
from collections import defaultdict
from pathlib import Path

# alternateNamesV2.txt column indices. The trailing columns are absent on most rows,
# so anything past COL_NAME has to be read defensively.
COL_NAME = 3
COL_ISPREFERRED = 4
COL_ISHISTORIC = 7

# isolanguage values in alternateNamesV2.txt that are reference codes rather than names
# a reader would ever see in prose: links, ids, postal and transport codes.
NON_NAME_LANGUAGES = frozenset({
    'link', 'wkdt', 'post', 'iata', 'icao', 'faac', 'unlc', 'tcid', 'phon', 'piny',
})

countries = {}
p_data = Path('datasets')


def read_alternate_names(geonameids):
    """{geonameid: {isolanguage: [name, ...]}} for the given ids, preferred names first.

    Streams alternateNamesV2.txt (~780 MB) once. Historic names and non-name reference
    codes are dropped; everything else is kept, so callers can pick their own languages.
    """
    path = p_data.joinpath('alternateNamesV2.txt')
    if not path.exists():
        print(f'{path} not found — run ./bin/download_data.py first')
        return {}

    names = defaultdict(lambda: defaultdict(list))
    with path.open(encoding='utf-8') as fh:
        for record in csv.reader(fh, 'excel-tab'):
            if len(record) <= COL_NAME:
                continue
            geonameid, isolanguage, name = record[1], record[2], record[COL_NAME]
            if geonameid not in geonameids or not name:
                continue
            is_historic = record[COL_ISHISTORIC] if len(record) > COL_ISHISTORIC else ''
            if is_historic == '1' or isolanguage in NON_NAME_LANGUAGES:
                continue
            is_preferred = (record[COL_ISPREFERRED] if len(record) > COL_ISPREFERRED else '') == '1'
            bucket = names[geonameid][isolanguage]
            bucket.insert(0, name) if is_preferred else bucket.append(name)
    return names

reader = csv.reader(p_data.joinpath('countryInfo.txt').open(encoding='utf-8'), 'excel-tab')
for record in reader:
    if record[0].startswith('#'):
        continue

    (
        iso,
        iso3,
        isonumeric,
        fips,
        name,
        capital,
        areakm2,
        population,
        continentcode,
        tld,
        currencycode,
        currencyname,
        phone,
        postalcodeformat,
        postalcoderegex,
        languages,
        geonameid,
        neighbours,
        equivalentfipscode,
    ) = record

    countries[iso] = {
        'geonameid': int(geonameid) if geonameid else 0,
        'name': name,
        'iso': iso,
        'iso3': iso3,
        'isonumeric': int(isonumeric),
        'fips': fips,
        'continentcode': continentcode,
        'capital': capital,
        'areakm2': int(float(areakm2)) if areakm2 else 0,
        'population': int(population) if population else 0,
        'tld': tld,
        'currencycode': currencycode,
        'currencyname': currencyname,
        'phone': phone,
        'postalcoderegex': postalcoderegex,
        'languages': languages,
        'neighbours': neighbours,
    }


alternate_names = read_alternate_names({str(c['geonameid']) for c in countries.values()})
for country in countries.values():
    by_language = alternate_names.get(str(country['geonameid']), {})
    country['alternatenames'] = dict(by_language)

p_data.joinpath('countries.json').write_text(json.dumps(countries), encoding='utf-8')
