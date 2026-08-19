from geonamescache import GeonamesCache

gc = GeonamesCache()


def test_get_admin1_codes():
    admin1 = gc.get_admin1_codes()
    assert len(admin1) > 3000
    for key, name, geonameid in (
        ('US.CA', 'California', 5332921),
        ('ES.51', 'Andalusia', 2593109),
    ):
        assert name == admin1[key]['name']
        assert geonameid == admin1[key]['geonameid']


def test_admin1_code_resolves_city_reference():
    # Cities store countrycode and admin1code separately, the composite
    # admin1 key allows resolving these references.
    city = gc.get_cities()['5368361']
    assert 'Los Angeles' == city['name']
    key = f"{city['countrycode']}.{city['admin1code']}"
    assert 'California' == gc.get_admin1_codes()[key]['name']


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
    assert 'Rotterdam' == city['name']
    assert '11' == city['admin1code']
    admin1 = gc.get_admin1_by_city(city)
    assert admin1 is not None
    assert 'South Holland' == admin1['name']


def test_get_admin2_by_city():
    city = gc.get_cities()['2747891']
    admin2 = gc.get_admin2_by_city(city)
    assert admin2 is not None
    assert 'Rotterdam' == admin2['name']
    assert 2747890 == admin2['geonameid']


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
    assert 'NL.11.0599' == key
    assert 'Rotterdam' == gc.get_admin2_codes()[key]['name']


def test_get_timezones():
    timezones = gc.get_timezones()
    assert len(timezones) > 400
    amsterdam = timezones['Europe/Amsterdam']
    assert 'NL' == amsterdam['countrycode']
    assert 1.0 == amsterdam['rawoffset']


def test_get_timezones_by_country():
    assert ['Europe/Amsterdam'] == [tz['timezoneid'] for tz in gc.get_timezones_by_country('NL')]

    # The US spans many zones, the list must be sorted by time zone id.
    us = [tz['timezoneid'] for tz in gc.get_timezones_by_country('US')]
    assert len(us) > 20
    assert us == sorted(us)
    assert 'Pacific/Honolulu' in us
    assert all('US' == tz['countrycode'] for tz in gc.get_timezones_by_country('US'))


def test_get_timezones_by_country_edge_cases():
    # Country codes are matched case insensitively.
    assert gc.get_timezones_by_country('nl') == gc.get_timezones_by_country('NL')

    # Unknown codes return an empty list rather than raising.
    assert [] == gc.get_timezones_by_country('ZZ')


def test_city_timezone_is_in_timezones():
    # Every timezone referenced by a city record must exist in the dataset.
    timezones = gc.get_timezones()
    assert all(city['timezone'] in timezones for city in gc.get_cities().values())


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

    assert small.cities_by_names is not large.cities_by_names

    small_hits = small.get_cities_by_name('Springfield')
    large_hits = large.get_cities_by_name('Springfield')
    assert len(large_hits) > len(small_hits)
