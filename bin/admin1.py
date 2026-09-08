#!/usr/bin/env python
"""Build admin1.json from the ADM1 records in allCountries.txt.

admin1CodesASCII.txt names each division after its preferred English alternate
name, which upstream lets go stale (VE.25 is still "Distrito Federal" there,
years after the rename to "Distrito Capital"). The ADM1 rows in allCountries
carry the current name, so they are the source of truth here. The English form
survives in alternatenames.
"""
import json
import sys
from pathlib import Path

# Index of the last allCountries.txt column this reads, and so the minimum column
# count a usable record has.
COL_ADMIN1CODE = 10

p_data = Path('datasets')
p_all = p_data.joinpath('allCountries.txt')

if not p_all.exists():
    sys.exit(f'{p_all} not found — run ./bin/download_data.py first')

admin1 = {}

# Plain splitting rather than csv: the file is ~1.8 GB and only five of the
# nineteen columns are needed.
with p_all.open(encoding='utf-8') as fh:
    for line in fh:
        record = line.rstrip('\n').split('\t')
        if len(record) <= COL_ADMIN1CODE or record[7] != 'ADM1':
            continue

        geonameid, name, asciiname, alternatenames = record[0], record[1], record[2], record[3]
        countrycode, admin1code = record[8], record[COL_ADMIN1CODE]

        # required because used as key
        if not countrycode or not admin1code:
            continue

        admin1[f'{countrycode}.{admin1code}'] = {
            'asciiname': asciiname,
            'geonameid': int(geonameid) if geonameid else 0,
            'name': name,
            'alternatenames': alternatenames.split(',') if alternatenames else [],
        }

p_data.joinpath('admin1.json').write_text(json.dumps(admin1, ensure_ascii=False), encoding='utf-8')
print(f'admin1: {len(admin1)} divisions')
