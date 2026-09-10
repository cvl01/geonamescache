from geonamescache import GeonamesCache

gc = GeonamesCache()


def test_get_admin1_codes():
    admin1 = gc.get_admin1_codes()
    assert len(admin1) > 3000
    for key, name, geonameid in (
        ('US.CA', 'California', 5332921),
        ('ES.51', 'Andalusia', 2593109),
        ('VE.25', 'Distrito Capital', 3640847),
    ):
        assert name == admin1[key]['name']
        assert geonameid == admin1[key]['geonameid']


def test_admin1_alternate_names_are_grouped_by_language():
    dutch = gc.get_admin1_codes()['NL.11']['alternatenames']
    assert 'South Holland' in dutch['en']
    assert 'Zuid-Holland' in dutch['nl']
    assert 'Súd-Hollân' in dutch['fy']


def test_admin1_alternate_names_exclude_foreign_languages():
    # Regression: names used to come from the untagged `alternatenames` column of
    # allCountries, which mixes in GeoNames' ASCII romanisation of every language it
    # holds. The Greek name for Qabala Rayon, Καμπάλα, romanises to a literal "Kampala",
    # so a scorer matching Uganda's capital in text voted for Azerbaijan.
    qabala = gc.get_admin1_codes()['AZ.38']
    assert 'Kampala' not in gc.get_admin1_names(qabala, historic=True)
    assert 'el' not in qabala['alternatenames']
    # Armenian is one of Azerbaijan's languages, so it stays, in its own script rather
    # than as the "Gabalayi srjan" romanisation.
    assert 'Գաբալայի շրջան' in qabala['alternatenames']['hy']


def test_admin1_alternate_names_exclude_reference_codes():
    languages = {lang for a in gc.get_admin1_codes().values() for lang in a['alternatenames']}
    assert not languages & {'link', 'wkdt', 'post', 'iata', 'icao', 'unlc', 'phon', 'piny'}


def test_admin1_englishname():
    # The English form the older admin1CodesASCII.txt named each division after, which
    # `name` no longer carries since it comes from the current allCountries ADM1 row.
    for key, name, english in (
        ('CD.11', 'Province du Nord-Kivu', 'North Kivu'),
        ('NL.11', 'Provincie Zuid-Holland', 'South Holland'),
        ('KE.05', 'Nairobi', 'Nairobi County'),
        ('NG.05', 'Lagos State', 'Lagos'),
    ):
        admin1 = gc.get_admin1_codes()[key]
        assert admin1['name'] == name
        assert admin1['englishname'] == english


def test_admin1_englishname_is_empty_when_there_is_no_english_row():
    admin1 = gc.get_admin1_codes()
    missing = [a for a in admin1.values() if not a['englishname']]
    assert missing
    assert all(a['alternatenames'].get('en', []) == [] for a in missing)


def test_get_admin1_names_puts_the_name_first_and_deduplicates():
    names = gc.get_admin1_names(gc.get_admin1_codes()['NG.11'])
    assert names[0] == 'Federal Capital Territory'
    assert len(names) == len(set(names))
    assert 'FCT' in names


def test_get_admin1_names_can_select_languages():
    # VE.25 renamed from Distrito Federal to Distrito Capital; both Spanish forms are
    # current in the source, so both must resolve.
    names = gc.get_admin1_names(gc.get_admin1_codes()['VE.25'], languages=('es',))
    assert 'Distrito Capital' in names
    assert 'Distrito Federal' in names


def test_get_admin1_names_always_includes_untagged_names_and_abbreviations():
    # Neither key is a language, so selecting languages must not drop them.
    names = gc.get_admin1_names(gc.get_admin1_codes()['NL.11'], languages=('en',))
    assert 'Sudholland' in names  # untagged
    assert 'zh' in names  # abbr, the Dutch abbreviation for Zuid-Holland
    assert 'Súd-Hollân' not in names  # fy, not selected


def test_get_admin1_names_historic_is_opt_in():
    western_australia = gc.get_admin1_codes()['AU.08']
    assert 'Swan River Colony' in western_australia['historicnames']['']
    assert 'Swan River Colony' not in gc.get_admin1_names(western_australia)
    assert 'Swan River Colony' in gc.get_admin1_names(western_australia, historic=True)


def test_admin1_code_resolves_city_reference():
    # Cities store countrycode and admin1code separately, the composite
    # admin1 key allows resolving these references.
    city = gc.get_cities()['5368361']
    assert city['name'] == 'Los Angeles'
    key = f"{city['countrycode']}.{city['admin1code']}"
    assert gc.get_admin1_codes()[key]['name'] == 'California'


def test_get_admin2_codes():
    admin2 = gc.get_admin2_codes()
    assert len(admin2) > 40000
    for key, name, geonameid in (
        ('NL.11.0599', 'Rotterdam', 2747890),
        ('US.CA.037', 'Los Angeles County', 5368381),
    ):
        assert name == admin2[key]['name']
        assert geonameid == admin2[key]['geonameid']


def test_get_admin1_by_city():
    city = gc.get_cities()['2747891']
    assert city['name'] == 'Rotterdam'
    assert city['admin1code'] == '11'
    admin1 = gc.get_admin1_by_city(city)
    assert admin1 is not None
    assert admin1['name'] == 'Provincie Zuid-Holland'


def test_get_admin2_by_city():
    city = gc.get_cities()['2747891']
    admin2 = gc.get_admin2_by_city(city)
    assert admin2 is not None
    assert admin2['name'] == 'Rotterdam'
    assert admin2['geonameid'] == 2747890


def test_get_admin_by_city_unresolvable():
    # Missing or unknown codes must return None rather than raise or build a
    # partial key such as 'NL.'.
    city = dict(gc.get_cities()['2747891'])
    for field in ('countrycode', 'admin1code', 'admin2code'):
        broken = {**city, field: ''}
        assert gc.get_admin2_by_city(broken) is None
    assert gc.get_admin1_by_city({**city, 'admin1code': ''}) is None
    assert gc.get_admin1_by_city({**city, 'admin1code': 'ZZ'}) is None


def test_admin2_code_resolves_city_reference():
    # Cities store countrycode, admin1code and admin2code separately, the
    # composite admin2 key allows resolving these references.
    city = gc.get_cities()['2747891']
    key = f"{city['countrycode']}.{city['admin1code']}.{city['admin2code']}"
    assert key == 'NL.11.0599'
    assert gc.get_admin2_codes()[key]['name'] == 'Rotterdam'


def test_get_timezones():
    timezones = gc.get_timezones()
    assert len(timezones) > 400
    amsterdam = timezones['Europe/Amsterdam']
    assert amsterdam['countrycode'] == 'NL'
    assert amsterdam['rawoffset'] == 1.0


def test_get_timezones_by_country():
    assert [tz['timezoneid'] for tz in gc.get_timezones_by_country('NL')] == ['Europe/Amsterdam']

    # The US spans many zones, the list must be sorted by time zone id.
    us = [tz['timezoneid'] for tz in gc.get_timezones_by_country('US')]
    assert len(us) > 20
    assert us == sorted(us)
    assert 'Pacific/Honolulu' in us
    assert all(tz['countrycode'] == 'US' for tz in gc.get_timezones_by_country('US'))


def test_get_timezones_by_country_edge_cases():
    # Country codes are matched case insensitively.
    assert gc.get_timezones_by_country('nl') == gc.get_timezones_by_country('NL')

    # Unknown codes return an empty list rather than raising.
    assert gc.get_timezones_by_country('ZZ') == []


def test_city_timezone_is_in_timezones():
    # Every timezone referenced by a city record must exist in the dataset.
    timezones = gc.get_timezones()
    assert all(city['timezone'] in timezones for city in gc.get_cities().values())


def test_city_featurecode():
    cities = gc.get_cities()
    assert cities['2747891']['featurecode'] == 'PPL'
    # Feature codes are never blank in these datasets.
    assert all(city['featurecode'] for city in cities.values())

    # PPLC marks the capital of a political entity, which is how the datasets
    # include capitals that fall below their population threshold.
    capitals = {city['name'] for city in cities.values() if city['featurecode'] == 'PPLC'}
    for capital in ('Nuuk', 'Belmopan', 'Madrid', 'Washington'):
        assert capital in capitals


def test_search_cities_by_featurecode():
    seats = gc.search_cities('PPLG', attribute='featurecode', contains_search=False)
    assert seats
    assert all(city['featurecode'] == 'PPLG' for city in seats)


def test_country_alternate_names_are_grouped_by_language():
    countries = gc.get_countries()
    dutch = countries['NL']['alternatenames']
    assert 'Pays-Bas' in dutch['fr']
    assert 'Niederlande' in dutch['de']
    assert 'Holland' in dutch['en']
    # Every country has at least one alternate name.
    assert all(country['alternatenames'] for country in countries.values())


def test_country_alternate_names_exclude_reference_codes():
    # link/wkdt/post/iata/... rows are ids and codes, not names anyone writes in prose.
    languages = {lang for c in gc.get_countries().values() for lang in c['alternatenames']}
    assert not languages & {'link', 'wkdt', 'post', 'iata', 'icao', 'unlc', 'phon', 'piny'}


def test_get_country_names_puts_the_name_first_and_deduplicates():
    names = gc.get_country_names(gc.get_countries()['GB'])
    assert names[0] == 'United Kingdom'
    assert len(names) == len(set(names))
    assert 'Reino Unido' in names
    assert 'Royaume-Uni' in names


def test_get_country_names_can_select_languages():
    names = gc.get_country_names(gc.get_countries()['GB'], languages=('pt',))
    assert 'Reino Unido' in names
    assert 'Royaume-Uni' not in names


def test_get_country_names_always_includes_unlanguaged_names():
    # "The Netherlands" is the record's name and its `en` names lack the bare form, which
    # sits under the empty-language key — selecting languages must not drop it.
    names = gc.get_country_names(gc.get_countries()['NL'], languages=('fr',))
    assert 'Netherlands' in names
    assert 'Pays-Bas' in names


def test_get_country_names_ignores_unknown_languages():
    names = gc.get_country_names(gc.get_countries()['NL'], languages=('zz',))
    assert 'Netherlands' in names


def test_get_countries_by_names():
    # Length of get_countries_by_names dict and get_countries dict must be
    # the same, unless country names wouldn't be unique.
    assert len(gc.get_countries_by_names()), len(gc.get_countries())


def test_get_cities_by_name():
    cities = gc.get_cities()
    for gid, name in (('3191316', 'Samobor'), ('3107112', 'Rivas-Vaciamadrid')):
        assert name == cities[gid]['name']


def test_get_cities_by_name_madrid():
    assert len(gc.get_cities_by_name('Madrid')) > 1


def test_get_cities_by_name_returns_city_records():
    rotterdams = gc.get_cities_by_name('Rotterdam')
    assert len(rotterdams) == 2
    # Records are returned directly, not wrapped in single-key dictionaries.
    assert sorted(city['countrycode'] for city in rotterdams) == ['NL', 'US']
    assert all(city['name'] == 'Rotterdam' for city in rotterdams)

    # The records are the same objects held by get_cities(), not copies.
    assert gc.get_cities()['2747891'] in rotterdams


def test_get_cities_by_name_unknown():
    assert gc.get_cities_by_name('Nonexistent Place') == []


def test_get_cities_by_names_index():
    index = gc.get_cities_by_names()
    assert index is gc.get_cities_by_names()

    # Every city must appear under its own name, and nothing may be lost.
    cities = gc.get_cities()
    assert sum(len(records) for records in index.values()) == len(cities)
    assert len(index) < len(cities)  # names are not unique
    for city in cities.values():
        assert city in index[city['name']]


def test_cities_in_us_states():
    cities = gc.get_cities()
    for gid, name, us_state in (('4164138', 'Miami', 'FL'), ('4525353', 'Springfield', 'OH')):
        assert name == cities[gid]['name']
        assert us_state == cities[gid]['admin1code']


def test_search_cities():
    cities = gc.search_cities('Kiev')
    assert len(cities) >= 1


def test_search_cities_case_sensitive():
    cities = gc.search_cities('Stoke-On-Trent', case_sensitive=True)
    assert len(cities) == 0
    cities = gc.search_cities('Stoke-On-Trent')
    assert len(cities) == 1


def test_search_cities_alternatenames_contains_search():
    assert (
        len(gc.search_cities('London'))
        > len(gc.search_cities('London', contains_search=False))
        > 1
    )


def test_search_cities_name_contains_search():
    assert (
        len(gc.search_cities('London', 'name'))
        > len(gc.search_cities('London', 'name', contains_search=False))
        > 1
    )


def test_search_cities_alternatenames_contains_search_and_case_sensitive():
    assert (
        len(gc.search_cities('London', case_sensitive=True))
        > len(gc.search_cities('London', case_sensitive=True, contains_search=False))
        > 1
    )


def test_search_cities_name_contains_search_and_case_sensitive():
    assert (
        len(gc.search_cities('London', 'name', case_sensitive=True))
        > len(gc.search_cities('London', 'name', case_sensitive=True, contains_search=False))
        > 1
    )


def test_datasets_are_cached_per_instance():
    # Regression: _load_data used to return the parsed data without storing it,
    # so every getter call re-read and re-parsed the JSON file from disk.
    instance = GeonamesCache()
    assert instance.cities is None
    first = instance.get_cities()
    assert instance.cities is not None
    assert first is instance.get_cities()

    for getter, attribute in (
        (instance.get_countries, 'countries'),
        (instance.get_admin1_codes, 'admin1'),
        (instance.get_admin2_codes, 'admin2'),
        (instance.get_timezones, 'timezones'),
        (instance.get_us_states, 'us_states'),
        (instance.get_us_counties, 'us_counties'),
    ):
        assert getattr(instance, attribute) is None
        assert getter() is getter()
        assert getattr(instance, attribute) is not None


def test_city_name_cache_is_not_shared_between_instances():
    # Regression: cities_by_names was a ClassVar keyed by name only, so an
    # instance with a larger dataset got served another instance's results.
    small = GeonamesCache(min_city_population=15000)
    large = GeonamesCache(min_city_population=500)

    assert small.get_cities_by_names() is not large.get_cities_by_names()

    small_hits = small.get_cities_by_name('Springfield')
    large_hits = large.get_cities_by_name('Springfield')
    assert len(large_hits) > len(small_hits)
