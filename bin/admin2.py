#!/usr/bin/env python
"""Build admin2.json from the ADM2 records in allCountries.txt.

admin2Codes.txt carries only a code, a name and an id, and names each division in
whatever form upstream settled on. The ADM2 rows in allCountries carry the current
local name, and reading them here lets the division be enriched with the same
language-keyed alternate names bin/admin1.py gives ADM1 — the only route to a
division's English or superseded forms.
"""
import json
import sys
from pathlib import Path

from _alternatenames import (
    ENGLISH,
    base_language,
    plain,
    read_alternate_names,
    read_country_languages,
)

# Index of the last allCountries.txt column this reads, and so the minimum column
# count a usable record has.
COL_ADMIN2CODE = 11

p_data = Path('datasets')
p_all = p_data.joinpath('allCountries.txt')
p_alternate = p_data.joinpath('alternateNamesV2.txt')
p_countryinfo = p_data.joinpath('countryInfo.txt')

for path in (p_all, p_alternate, p_countryinfo):
    if not path.exists():
        sys.exit(f'{path} not found — run ./bin/download_data.py first')

admin2 = {}
country_by_id = {}

# Plain splitting rather than csv: the file is ~1.8 GB and only seven of the
# nineteen columns are needed.
with p_all.open(encoding='utf-8') as fh:
    for line in fh:
        record = line.rstrip('\n').split('\t')
        if len(record) <= COL_ADMIN2CODE or record[7] != 'ADM2':
            continue

        geonameid, name, asciiname = record[0], record[1], record[2]
        latitude, longitude = record[4], record[5]
        countrycode, admin1code = record[8], record[10]
        admin2code = record[COL_ADMIN2CODE]

        # all three are required because they form the key
        if not countrycode or not admin1code or not admin2code:
            continue

        admin2[f'{countrycode}.{admin1code}.{admin2code}'] = {
            'admin1code': admin1code,
            'admin2code': admin2code,
            'asciiname': asciiname,
            'countrycode': countrycode,
            'geonameid': int(geonameid) if geonameid else 0,
            'latitude': float(latitude),
            'longitude': float(longitude),
            'name': name,
        }
        country_by_id[geonameid] = countrycode

languages_by_country = read_country_languages(p_countryinfo)
current, historic = read_alternate_names(p_alternate, country_by_id, languages_by_country)

for division in admin2.values():
    geonameid = str(division['geonameid'])
    names = plain(current, geonameid)
    english = names.get(ENGLISH) or [
        n for code, bucket in sorted(names.items()) if base_language(code) == ENGLISH for n in bucket
    ]
    division['englishname'] = english[0] if english else ''
    division['alternatenames'] = names
    division['historicnames'] = plain(historic, geonameid)

p_data.joinpath('admin2.json').write_text(json.dumps(admin2, ensure_ascii=False), encoding='utf-8')
print(f'admin2: {len(admin2)} divisions')
