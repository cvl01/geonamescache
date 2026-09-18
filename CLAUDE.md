# geonamescache

## Before every push

Run the same checks CI runs, with the same tool. `uvx ruff check` is **not** enough:
`hatch check code` uses a stricter rule set and catches things plain ruff does not
(`FBT001` on boolean positional arguments, `SLF001` on private access from tests).
Every push that skipped it has failed in CI.

    uvx hatch check code
    uvx hatch run geonamescache-dev:type_check
    uvx hatch test --randomize
    uvx hatch build --clean

A release adds nothing to that list: `.github/workflows/release.yml` runs static
analysis and the tests before it builds, so a failure there leaves the release with
its previous assets.

## Data pipeline

`geonamescache/data/` is gitignored and built from `datasets/`, so a wheel can only be
built after the pipeline has run:

    make dl    # ~2.6 GB of GeoNames dumps, skips what is already in datasets/
    make json  # builds every dataset, then gzips it into geonamescache/data/

`bin/cities.py` and `bin/admin{1,2}.py` all stream `alternateNamesV2.txt` (~780 MB)
and each takes minutes. Run them in the background rather than blocking on them.

## Alternate names

Never read the `alternatenames` column of `allCountries.txt` or the cities dumps. It is
untagged and mixes in GeoNames' own ASCII romanisation of every language a place has a
name in, and those romanisations collide across languages. `bin/_alternatenames.py`
reads `alternateNamesV2.txt` instead, which holds none of them, and keeps only the
languages the place's own country speaks plus English. Anything new that needs names
goes through that module.
