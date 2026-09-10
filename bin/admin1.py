#!/usr/bin/env python
"""Build admin1.json from the ADM1 records in allCountries.txt.

admin1CodesASCII.txt names each division after its preferred English alternate
name, which upstream lets go stale (VE.25 is still "Distrito Federal" there,
years after the rename to "Distrito Capital"). The ADM1 rows in allCountries
carry the current name, so they are the source of truth here. The English form
is recovered from the `en` alternate names instead, which is what upstream
derives admin1CodesASCII from in the first place.
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
COL_ADMIN1CODE = 10

p_data = Path('datasets')
p_all = p_data.joinpath('allCountries.txt')
p_alternate = p_data.joinpath('alternateNamesV2.txt')
p_countryinfo = p_data.joinpath('countryInfo.txt')

for path in (p_all, p_alternate, p_countryinfo):
    if not path.exists():
        sys.exit(f'{path} not found — run ./bin/download_data.py first')

admin1 = {}
country_by_id = {}

# Plain splitting rather than csv: the file is ~1.8 GB and only six of the
# nineteen columns are needed.
with p_all.open(encoding='utf-8') as fh:
    for line in fh:
        record = line.rstrip('\n').split('\t')
        if len(record) <= COL_ADMIN1CODE or record[7] != 'ADM1':
            continue

        geonameid, name, asciiname = record[0], record[1], record[2]
        countrycode, admin1code = record[8], record[COL_ADMIN1CODE]

        # required because used as key
        if not countrycode or not admin1code:
            continue

        admin1[f'{countrycode}.{admin1code}'] = {
            'asciiname': asciiname,
            'geonameid': int(geonameid) if geonameid else 0,
            'name': name,
        }
        country_by_id[geonameid] = countrycode

languages_by_country = read_country_languages(p_countryinfo)
current, historic = read_alternate_names(p_alternate, country_by_id, languages_by_country)

for division in admin1.values():
    geonameid = str(division['geonameid'])
    names = plain(current, geonameid)
    # Preferred names come first, so the head of the English bucket is the form
    # admin1CodesASCII.txt would name the division after. Plain `en` wins over the
    # region variants, which are rarer and no more authoritative.
    english = names.get(ENGLISH) or [
        n for code, bucket in sorted(names.items()) if base_language(code) == ENGLISH for n in bucket
    ]
    division['englishname'] = english[0] if english else ''
    division['alternatenames'] = names
    division['historicnames'] = plain(historic, geonameid)

p_data.joinpath('admin1.json').write_text(json.dumps(admin1, ensure_ascii=False), encoding='utf-8')
print(f'admin1: {len(admin1)} divisions')
