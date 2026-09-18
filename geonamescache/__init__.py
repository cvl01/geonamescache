__title__ = 'geonamescache'
__version__ = '5.0.0'
__author__ = 'Ramiro Gómez'
__license__ = 'MIT'


import gzip
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any, TypeVar

from geonamescache.types import (
    Admin1,
    Admin1CodeStr,
    Admin2,
    Admin2CodeStr,
    City,
    CitySearchAttribute,
    Continent,
    ContinentCode,
    Country,
    GeoNameIdStr,
    ISOStr,
    TimeZoneIdStr,
    TimeZoneInfo,
    USCounty,
    USState,
    USStateCode,
    USStateName,
)

TDict = TypeVar('TDict', bound=Mapping[str, Any])

# Alternate name keys on a division that are not a language, and so are never filtered
# out: the empty string for untagged names, `abbr` for abbreviations such as `NL.11`'s
# "zh" for Zuid-Holland. Country records predate `abbr` being treated this way and keep
# it selectable like any other key.
AGNOSTIC_KEYS = ('', 'abbr')


def _flatten(
    name: str,
    by_language: Mapping[str, list[str]],
    languages: Iterable[str] | None,
    always: tuple[str, ...],
) -> list[str]:
    """*name* followed by the selected language buckets, deduplicated, empties dropped.

    *always* names the buckets included whatever *languages* says, because their key is
    not a language: the empty string for untagged names, `abbr` for abbreviations.
    """
    wanted = list(by_language.keys() if languages is None else languages)
    for key in reversed(always):
        if key not in wanted:
            wanted.insert(0, key)
    names = [name]
    for language in wanted:
        names.extend(by_language.get(language, []))
    return [n for n in dict.fromkeys(names) if n]


def _record_names(
    record: Mapping[str, Any], languages: Iterable[str] | None, historic: bool
) -> list[str]:
    """A division's or city's `name` plus its alternate names, deduplicated, name first."""
    names = _flatten(record['name'], record['alternatenames'], languages, AGNOSTIC_KEYS)
    if historic:
        extra = _flatten('', record['historicnames'], languages, AGNOSTIC_KEYS)
        names += [n for n in extra if n not in names]
    return names


class GeonamesCache:
    admin1: dict[Admin1CodeStr, Admin1] | None = None
    admin2: dict[Admin2CodeStr, Admin2] | None = None
    continents: dict[ContinentCode, Continent] | None = None
    countries: dict[ISOStr, Country] | None = None
    cities: dict[GeoNameIdStr, City] | None = None
    timezones: dict[TimeZoneIdStr, TimeZoneInfo] | None = None
    us_counties: list[USCounty] | None = None
    us_states: dict[USStateCode, USState] | None = None

    def __init__(self, min_city_population: int = 15000):
        self.min_city_population = min_city_population
        # Per instance, because they index one particular cities dataset.
        self.cities_by_names: dict[str, list[City]] | None = None
        self._cities_by_country: dict[str, list[City]] | None = None
        # Keyed by the searched attribute, then by country code, then by casefolded value.
        self._city_by_value: dict[str, dict[str, dict[str, list[City]]]] = {}
        # Keyed by (admin level, whether historic names are included).
        self._admin_by_name: dict[tuple[int, bool], dict[str, list[Any]]] = {}

    def get_dataset_by_key(self, dataset: dict[Any, TDict], key: str) -> dict[Any, TDict]:
        return {d[key]: d for c, d in list(dataset.items())}

    def get_continents(self) -> dict[ContinentCode, Continent]:
        if self.continents is None:
            self.continents = self._load_data('continents')
        return self.continents

    def get_countries(self) -> dict[ISOStr, Country]:
        if self.countries is None:
            self.countries = self._load_data('countries')
        return self.countries

    def get_admin1_codes(self) -> dict[Admin1CodeStr, Admin1]:
        """Get first-level administrative divisions keyed by <countrycode>.<admin1code>, e. g. US.CA."""
        if self.admin1 is None:
            self.admin1 = self._load_data('admin1')
        return self.admin1

    def get_admin2_codes(self) -> dict[Admin2CodeStr, Admin2]:
        """Get second-level administrative divisions keyed by <countrycode>.<admin1code>.<admin2code>, e. g. NL.11.0599."""
        if self.admin2 is None:
            self.admin2 = self._load_data('admin2')
        return self.admin2

    def get_admin1_by_city(self, city: City) -> Admin1 | None:
        """Get the first-level administrative division a city belongs to, None if unresolvable.

        Not every city record has an admin1code, and not every code pair is
        present in the admin1 dataset, so callers should handle None.
        """
        if not city.get('countrycode') or not city.get('admin1code'):
            return None
        return self.get_admin1_codes().get(f"{city['countrycode']}.{city['admin1code']}")

    def get_admin2_by_city(self, city: City) -> Admin2 | None:
        """Get the second-level administrative division a city belongs to, None if unresolvable.

        Requires all three of countrycode, admin1code and admin2code, as the
        admin2 dataset is keyed by the concatenation of them.
        """
        if not city.get('countrycode') or not city.get('admin1code') or not city.get('admin2code'):
            return None
        return self.get_admin2_codes().get(f"{city['countrycode']}.{city['admin1code']}.{city['admin2code']}")

    def get_timezones(self) -> dict[TimeZoneIdStr, TimeZoneInfo]:
        """Get time zones keyed by IANA time zone id, e. g. Europe/Amsterdam."""
        if self.timezones is None:
            self.timezones = self._load_data('timezones')
        return self.timezones

    def get_timezones_by_country(self, countrycode: str) -> list[TimeZoneInfo]:
        """Get the time zones of a country as a list sorted by time zone id.

        Takes an ISO alpha-2 country code, case insensitive. Returns an empty
        list for unknown codes.
        """
        countrycode = countrycode.upper()
        return sorted(
            (tz for tz in self.get_timezones().values() if tz['countrycode'] == countrycode),
            key=lambda tz: tz['timezoneid'],
        )

    def get_us_states(self) -> dict[USStateCode, USState]:
        if self.us_states is None:
            self.us_states = self._load_data('us_states')
        return self.us_states

    def get_countries_by_names(self) -> dict[str, Country]:
        return self.get_dataset_by_key(self.get_countries(), 'name')

    def get_country_names(
        self, country: Country, *, languages: Iterable[str] | None = None
    ) -> list[str]:
        """The country's `name` plus its alternate names, deduplicated, name first.

        Country alternate names are stored per language because there are a lot of them
        (~43,600 across all countries, 163 languages for the United Kingdom alone), so a
        caller matching text in a few languages can take just those. *languages* selects
        ISO-639 codes to include, defaulting to every language in the record; an unknown
        code contributes nothing rather than raising.

        Names recorded without a language (the empty-string key) are **always** included:
        they are language-agnostic, and some are the form most used in English — the
        Netherlands' `name` is "The Netherlands" and its `en` names do not include the bare
        "Netherlands", which sits under that key.
        """
        return _flatten(country['name'], country['alternatenames'], languages, ('',))

    def get_admin1_names(
        self, admin1: Admin1, *, languages: Iterable[str] | None = None, historic: bool = False
    ) -> list[str]:
        """The division's `name` plus its alternate names, deduplicated, name first.

        Same shape and rules as `get_country_names()`. Unlike countries, a division only
        carries names in the languages of its own country plus English, so passing
        *languages* narrows an already narrow set — mostly useful to take just `en`.
        Untagged names and abbreviations are always included, whatever *languages* says,
        so `languages=('en',)` on `NL.11` still yields "zh", the Dutch abbreviation.

        Set *historic* to append names the source marks as superseded, e. g. `AU.08`'s
        "Swan River Colony" for what is now the State of Western Australia. They are kept
        out by default because a historic name can now belong to somewhere else entirely.
        Only 140 of the 3865 divisions have any: GeoNames flags the column sparsely, so
        an unflagged name is not evidence that the name is current.
        """
        return _record_names(admin1, languages, historic)

    def get_us_states_by_names(self) -> dict[USStateName, USState]:
        return self.get_dataset_by_key(self.get_us_states(), 'name')

    def get_cities(self) -> dict[GeoNameIdStr, City]:
        """Get a dictionary of cities keyed by geonameid."""
        if self.cities is None:
            self.cities = self._load_data(f'cities{self.min_city_population}')
        return self.cities

    def get_cities_by_names(self) -> dict[str, list[City]]:
        """Get city records grouped by name.

        City names are not unique, so each name maps to a list of records.
        """
        if self.cities_by_names is None:
            index: dict[str, list[City]] = {}
            for city in self.get_cities().values():
                index.setdefault(city['name'], []).append(city)
            self.cities_by_names = index
        return self.cities_by_names

    def get_cities_by_name(self, name: str) -> list[City]:
        """Get the city records with the given name, empty list if there are none.

        Builds an index of all city names on first call, so looking up many
        names costs one pass over the dataset rather than one pass per name.
        """
        return self.get_cities_by_names().get(name, [])

    def get_city_names(
        self, city: City, *, languages: Iterable[str] | None = None, historic: bool = False
    ) -> list[str]:
        """The city's `name` plus its alternate names, deduplicated, name first.

        Same shape and rules as `get_admin1_names()`: a city carries names only in the
        languages of its own country plus English, untagged names and abbreviations are
        always included whatever *languages* says, and *historic* appends names the
        source marks as superseded, which can now belong to somewhere else.
        """
        return _record_names(city, languages, historic)

    def get_us_counties(self) -> list[USCounty]:
        if self.us_counties is None:
            self.us_counties = self._load_data('us_counties')
        return self.us_counties

    def search_cities(
        self,
        query: str,
        attribute: CitySearchAttribute = 'alternatenames',
        *,
        countrycode: str | None = None,
        admin1code: str | None = None,
        case_sensitive: bool = False,
        contains_search: bool = True,
    ) -> list[City]:
        """Search all city records and return list of records, that match query for given attribute.

        *countrycode* and *admin1code* restrict the search before the name comparison, which
        is what makes a common toponym usable: "Santa Rosa" is hundreds of places worldwide
        and one inside a given province. *admin1code* takes the bare code (`11`) or the
        composite one (`CO.11`), and is ignored unless *countrycode* is given too.

        An exact, case insensitive search is answered from an index of every value keyed by
        country and casefolded value, built once per attribute; the other combinations scan,
        but a *countrycode* narrows what they scan to that country's records. Results come
        out in country order rather than geonameid order when the index is used.
        """
        countrycode = countrycode.upper() if countrycode else None
        admin1code = admin1code.rsplit('.', 1)[-1] if admin1code else None

        def in_scope(record: City) -> bool:
            return not (countrycode and admin1code and record['admin1code'] != admin1code)

        if not contains_search and not case_sensitive:
            index = self._city_value_index(attribute)
            buckets = [index.get(countrycode, {})] if countrycode else list(index.values())
            needle = query.casefold()
            return [r for bucket in buckets for r in bucket.get(needle, []) if in_scope(r)]

        needle = query if case_sensitive else query.casefold()
        results = []
        for record in self._city_candidates(countrycode):
            if not in_scope(record):
                continue
            values = self._city_values(record, attribute)
            if not case_sensitive:
                values = [v.casefold() for v in values]
            if any(needle in v for v in values) if contains_search else needle in values:
                results.append(record)
        return results

    def _city_candidates(self, countrycode: str | None) -> Iterable[City]:
        """The records a scanning search has to look at, narrowed to one country when given."""
        if countrycode is None:
            return self.get_cities().values()
        if self._cities_by_country is None:
            index: dict[str, list[City]] = {}
            for city in self.get_cities().values():
                index.setdefault(city['countrycode'], []).append(city)
            self._cities_by_country = index
        return self._cities_by_country.get(countrycode, [])

    @staticmethod
    def _city_values(record: City, attribute: CitySearchAttribute) -> list[str]:
        """The strings an attribute contributes: every bucket of a language-keyed one, else itself."""
        value: Any = record[attribute]
        if isinstance(value, dict):
            return [name for bucket in value.values() for name in bucket]
        return [value]

    def _city_value_index(self, attribute: CitySearchAttribute) -> dict[str, dict[str, list[City]]]:
        """Country code -> casefolded value -> city records. Built once per attribute.

        Keyed by country first so a scoped search touches one country's names only, which is
        the same trade `get_cities_by_names()` makes for the primary name: one pass over the
        dataset instead of one per query.
        """
        index = self._city_by_value.get(attribute)
        if index is None:
            index = {}
            for record in self.get_cities().values():
                by_value = index.setdefault(record['countrycode'], {})
                for value in self._city_values(record, attribute):
                    bucket = by_value.setdefault(value.casefold(), [])
                    # A record's values are added together, so a repeat is always the last
                    # entry and identity is enough to spot it.
                    if not bucket or bucket[-1] is not record:
                        bucket.append(record)
            self._city_by_value[attribute] = index
        return index

    def search_admin1(
        self,
        query: str,
        *,
        countrycode: str | None = None,
        case_sensitive: bool = False,
        contains_search: bool = False,
        historic: bool = False,
    ) -> list[Admin1]:
        """First-level divisions whose name, asciiname, englishname or alternate name matches.

        See `search_admin2()` for the shared rules.
        """
        return self._search_admin(
            1,
            query,
            countrycode,
            None,
            case_sensitive=case_sensitive,
            contains_search=contains_search,
            historic=historic,
        )

    def search_admin2(
        self,
        query: str,
        *,
        countrycode: str | None = None,
        admin1code: str | None = None,
        case_sensitive: bool = False,
        contains_search: bool = False,
        historic: bool = False,
    ) -> list[Admin2]:
        """Second-level divisions whose name, asciiname, englishname or alternate name matches.

        *countrycode* and *admin1code* restrict the search to one country and one of its
        first-level divisions, which is the difference between a usable answer and every
        namesake on earth — "Santa Rosa" names dozens of divisions. *admin1code* takes the
        bare code (`11`) or the composite one (`CO.11`), and is ignored without *countrycode*.

        Matching is exact by default, unlike `search_cities()`: a substring search on a word
        as common as "north" returns hundreds of divisions and settles nothing. *historic*
        adds names the source marks as superseded, which can now belong somewhere else.
        """
        return self._search_admin(
            2,
            query,
            countrycode,
            admin1code,
            case_sensitive=case_sensitive,
            contains_search=contains_search,
            historic=historic,
        )

    def _search_admin(
        self,
        level: int,
        query: str,
        countrycode: str | None,
        admin1code: str | None,
        *,
        case_sensitive: bool,
        contains_search: bool,
        historic: bool,
    ) -> Any:
        countrycode = countrycode.upper() if countrycode else None
        admin1code = admin1code.rsplit('.', 1)[-1] if admin1code else None

        def in_scope(record: Mapping[str, Any]) -> bool:
            if countrycode and record['countrycode'] != countrycode:
                return False
            return not (countrycode and admin1code and record['admin1code'] != admin1code)

        if not contains_search and not case_sensitive:
            index = self._admin_name_index(level, historic=historic)
            return [r for r in index.get(query.casefold(), []) if in_scope(r)]

        needle = query if case_sensitive else query.casefold()
        results = []
        for record in self._admin_records(level).values():
            if not in_scope(record):
                continue
            names = self._admin_names(record, historic=historic)
            if not case_sensitive:
                names = [n.casefold() for n in names]
            if any(needle in n for n in names) if contains_search else needle in names:
                results.append(record)
        return results

    def _admin_records(self, level: int) -> dict[str, Any]:
        return self.get_admin1_codes() if level == 1 else self.get_admin2_codes()  # type: ignore[return-value]

    @staticmethod
    def _admin_names(record: Mapping[str, Any], *, historic: bool) -> list[str]:
        """Every name a division should be findable under, in no particular order."""
        names = [record['name'], record['asciiname'], record.get('englishname') or '']
        fields = ('alternatenames', 'historicnames') if historic else ('alternatenames',)
        for field in fields:
            for bucket in (record.get(field) or {}).values():
                names.extend(bucket)
        return [n for n in names if n]

    def _admin_name_index(self, level: int, *, historic: bool) -> dict[str, list[Any]]:
        """Casefolded name -> division records. Built once per level, as names are not unique."""
        index = self._admin_by_name.get((level, historic))
        if index is None:
            index = {}
            for record in self._admin_records(level).values():
                for name in self._admin_names(record, historic=historic):
                    bucket = index.setdefault(name.casefold(), [])
                    if record not in bucket:
                        bucket.append(record)
            self._admin_by_name[level, historic] = index
        return index

    @staticmethod
    def _load_data(dataset: str) -> Any:
        """Read and parse a bundled dataset. Callers are responsible for caching."""
        path = os.path.join(os.path.dirname(__file__), 'data', dataset + '.json.gz')
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
