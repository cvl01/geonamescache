"""Reader for alternateNamesV2.txt, the only language-tagged source of names.

The `alternatenames` column in allCountries.txt and the cities dumps is a flat,
untagged mixture that also holds GeoNames' own ASCII romanisations of every language
it has a name in. Those romanisations collide across languages: the Greek name for
Azerbaijan's Qabala Rayon, Καμπάλα, romanises to a literal "Kampala", which is also
Greek for Uganda's capital. Reading this file instead drops the romanisations, which
exist nowhere in it, and lets the build keep only the languages a division is
plausibly written in.

bin/countries.py reads the same file with its own loop, because country records keep
every language rather than filtering to the country's own.
"""
import csv
from collections import defaultdict
from pathlib import Path

# alternateNamesV2.txt column indices. The trailing columns are absent on most rows,
# so anything past COL_NAME has to be read defensively.
COL_GEONAMEID = 1
COL_ISOLANGUAGE = 2
COL_NAME = 3
COL_ISPREFERRED = 4
COL_ISHISTORIC = 7

# isolanguage values that are reference codes rather than names a reader would ever
# see in prose: links, ids, postal and transport codes. Redundant against the language
# whitelist below, which excludes them anyway, but named here so the intent is explicit.
NON_NAME_LANGUAGES = frozenset({
    'link', 'wkdt', 'post', 'iata', 'icao', 'faac', 'unlc', 'tcid', 'phon', 'piny',
})

# isolanguage values kept whatever the division's country. The empty string is an
# untagged name, which is language-agnostic and often the form used in English;
# `abbr` is an abbreviation, e. g. "DC" for the District of Columbia.
LANGUAGE_AGNOSTIC = frozenset({'', 'abbr'})

ENGLISH = 'en'


def base_language(code: str) -> str:
    """The bare language subtag of an IETF-ish tag: en-US -> en, zh-Hans -> zh."""
    return code.split('-')[0].lower()


def read_country_languages(path: Path) -> dict[str, frozenset[str]]:
    """{countrycode: {language subtag, ...}} from countryInfo.txt, English always included.

    The `Languages` column is a comma separated list of region tagged codes
    (`nl-BE,fr-BE,de-BE`), reduced here to bare subtags so it can be matched against
    the isolanguage column, which tags the same language differently (`en-US`, `zh-Hans`).
    """
    languages = {}
    with path.open(encoding='utf-8') as fh:
        for record in csv.reader(fh, 'excel-tab'):
            if not record or record[0].startswith('#'):
                continue
            spoken = {base_language(code) for code in record[15].split(',') if code}
            languages[record[0]] = frozenset(spoken | {ENGLISH})
    return languages


def read_alternate_names(
    path: Path,
    country_by_id: dict[str, str],
    languages_by_country: dict[str, frozenset[str]],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, dict[str, list[str]]]]:
    """Current and historic names for the given ids, as {geonameid: {isolanguage: [name]}}.

    Streams alternateNamesV2.txt (~780 MB) once. A row is kept when its isolanguage is
    language-agnostic, or its base subtag is one of the country's own languages or
    English; every other language, and every non-name reference code, is dropped.
    Preferred names come first within each language.

    *country_by_id* maps the wanted geonameids to their country code and so doubles as
    the set of ids to collect. Ids whose country is unknown keep only the
    language-agnostic and English rows.
    """
    current: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    historic: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    english_only = frozenset({ENGLISH})

    with path.open(encoding='utf-8') as fh:
        for record in csv.reader(fh, 'excel-tab'):
            if len(record) <= COL_NAME:
                continue
            country = country_by_id.get(record[COL_GEONAMEID])
            if country is None:
                continue

            isolanguage, name = record[COL_ISOLANGUAGE], record[COL_NAME]
            if not name or isolanguage in NON_NAME_LANGUAGES:
                continue
            if isolanguage not in LANGUAGE_AGNOSTIC:
                spoken = languages_by_country.get(country, english_only)
                if base_language(isolanguage) not in spoken:
                    continue

            target = historic if _flag(record, COL_ISHISTORIC) else current
            bucket = target[record[COL_GEONAMEID]][isolanguage]
            bucket.insert(0, name) if _flag(record, COL_ISPREFERRED) else bucket.append(name)

    return current, historic


def _flag(record: list[str], column: int) -> bool:
    return len(record) > column and record[column] == '1'


def plain(names: dict[str, dict[str, list[str]]], geonameid: str) -> dict[str, list[str]]:
    """A geonameid's names as plain dicts, ready to serialise. Empty when it has none."""
    return {language: list(values) for language, values in names.get(geonameid, {}).items()}
