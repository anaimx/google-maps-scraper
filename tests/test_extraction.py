import json
import os
import csv
import pytest
from gmaps_scraper import (
    BusinessPlace,
    parse_coordinates_from_url,
    is_valid_business,
    build_search_url,
    save_results,
    main,
)

def test_coordinate_parsing_prefers_pin_coordinates_over_viewport():
    """
    Test 1: Given a URL with both @camera viewport coordinates and !3d/!4d pin coordinates,
    assert that parse_coordinates_from_url extracts the !3d and !4d pin coordinates,
    not the @camera viewport coordinates.
    """
    # Camera viewport is @37.7749000,-122.4194000,15z
    # Exact business pin is !3d37.7891234!4d-122.4012345
    url_with_pin_and_camera = (
        "https://www.google.com/maps/place/Some+Store/@37.7749000,-122.4194000,15z"
        "/data=!4m6!3m5!1s0x8085806377777777:0x123456789abcdef0!8m2!3d37.7891234!4d-122.4012345!16s%2Fg%2F11test"
    )
    lat, lng = parse_coordinates_from_url(url_with_pin_and_camera)
    assert lat == pytest.approx(37.7891234)
    assert lng == pytest.approx(-122.4012345)

def test_coordinate_parsing_fallback_to_camera_viewport():
    """
    When !3d and !4d pin coordinates are absent, fall back to @camera viewport.
    """
    url_only_camera = "https://www.google.com/maps/place/Some+Store/@40.7128,-74.0060,14z"
    lat, lng = parse_coordinates_from_url(url_only_camera)
    assert lat == pytest.approx(40.7128)
    assert lng == pytest.approx(-74.0060)

def test_coordinate_parsing_negative_coordinates():
    """Handles southern/eastern hemisphere negative/positive combinations."""
    url_sydney = (
        "https://www.google.com/maps/place/Sydney+Harbour+Coffee/@-33.8568,151.2153,17z"
        "/data=!4m6!3m5!1s0x...:0x...!8m2!3d-33.8567844!4d151.2152967"
    )
    lat, lng = parse_coordinates_from_url(url_sydney)
    assert lat == pytest.approx(-33.8567844)
    assert lng == pytest.approx(151.2152967)

def test_coordinate_parsing_invalid_url():
    """Returns (None, None) when no coordinates are found in URL."""
    url_no_coords = "https://www.google.com/maps/search/coffee+shop"
    lat, lng = parse_coordinates_from_url(url_no_coords)
    assert lat is None
    assert lng is None

    assert parse_coordinates_from_url("") == (None, None)

def test_coordinate_parsing_order_agnostic():
    """
    Assert that parse_coordinates_from_url correctly extracts coordinates
    when !4d (longitude) appears before !3d (latitude) in the URL.
    """
    url_lng_before_lat = (
        "https://www.google.com/maps/place/Custom+Shop/@3.1390,101.6869,15z"
        "/data=!4m6!3m5!1s0x0:0x0!8m2!4d101.6868550!3d3.1390030!16s%2Fg%2F11test"
    )
    lat, lng = parse_coordinates_from_url(url_lng_before_lat)
    assert lat == pytest.approx(3.1390030)
    assert lng == pytest.approx(101.6868550)

def test_is_valid_business_rejects_administrative_locality_cards():
    """
    Test 2: Locality filter: assert that is_valid_business() rejects locality cards
    (empty rating/phone, or category='City'/'Town'/etc.) and accepts valid businesses.
    """
    locality_city = BusinessPlace(
        name="Edinburgh",
        category="City",
        rating=None,
        reviews_count=None,
        phone="",
        address="Edinburgh, UK"
    )
    assert not is_valid_business(locality_city)

    locality_district = BusinessPlace(
        name="Downtown",
        category="District",
        rating=None,
        reviews_count=None,
        phone="",
        address=""
    )
    assert not is_valid_business(locality_district)

    locality_empty_business = BusinessPlace(
        name="Florence",
        category="",
        rating=None,
        reviews_count=None,
        phone="",
        address=""
    )
    assert not is_valid_business(locality_empty_business)

    # Empty name
    no_name = BusinessPlace(
        name="",
        category="Coffee shop",
        rating=4.5,
        reviews_count=10,
        phone="12345",
        address="Some St"
    )
    assert not is_valid_business(no_name)

    # Commercial category but zero details (no address, phone, rating, reviews, website)
    empty_details = BusinessPlace(
        name="Ghost Place",
        category="Coffee shop",
        rating=None,
        reviews_count=None,
        phone="",
        address="",
        website=""
    )
    assert not is_valid_business(empty_details)

def test_is_valid_business_rejects_ghost_listings():
    """
    Assert that ghost/abandoned listings with a valid category (e.g. 'Car wash')
    but NO rating, NO review count, and NO phone number are rejected.
    """
    ghost_car_wash = BusinessPlace(
        name="Petaling jaya",
        category="Car wash",
        rating=None,
        reviews_count=None,
        phone="",
        address="Petaling Jaya, Selangor"
    )
    assert not is_valid_business(ghost_car_wash)

    ghost_art_gallery = BusinessPlace(
        name="Galleria dell'Arte",
        category="Art gallery",
        rating=None,
        reviews_count=None,
        phone="",
        address="Via dei Cerchi 8, Florence, Italy"
    )
    assert not is_valid_business(ghost_art_gallery)

    ghost_whitespace_phone = BusinessPlace(
        name="Abandoned Bakery",
        category="Bakery",
        rating=None,
        reviews_count=None,
        phone="   ",
        address="123 High St"
    )
    assert not is_valid_business(ghost_whitespace_phone)

def test_is_valid_business_accepts_valid_businesses():
    """Valid business with credible signals (rating, review count, or phone)."""
    # Has rating & reviews & phone
    business_full = BusinessPlace(
        name="The Daily Drip",
        category="Coffee shop",
        rating=4.7,
        reviews_count=120,
        phone="+1 206-555-0100",
        address="123 Pike St, Seattle, WA"
    )
    assert is_valid_business(business_full)

    # Place with phone but no rating is accepted
    business_with_phone_no_rating = BusinessPlace(
        name="Edinburgh Rare Books",
        category="Bookstore",
        rating=None,
        reviews_count=None,
        phone="+44 131 555 0199",
        address="45 High St, Edinburgh, UK"
    )
    assert is_valid_business(business_with_phone_no_rating)

    # Place with rating but no phone is accepted
    business_with_rating_no_phone = BusinessPlace(
        name="Seattle Roasters",
        category="Coffee shop",
        rating=4.5,
        reviews_count=50,
        phone="",
        address="100 Pine St, Seattle, WA"
    )
    assert is_valid_business(business_with_rating_no_phone)

    # Place with reviews_count but no rating and no phone is accepted
    business_with_reviews_only = BusinessPlace(
        name="Corner Bistro",
        category="Restaurant",
        rating=None,
        reviews_count=15,
        phone="",
        address="12 Market St"
    )
    assert is_valid_business(business_with_reviews_only)

def test_build_search_url_with_and_without_country():
    """
    Test 3: Search URL construction with country code (gl).
    """
    # Without country parameter
    url_default = build_search_url("coffee shop seattle")
    assert url_default == "https://www.google.com/maps/search/coffee+shop+seattle?hl=en"

    # With country parameter
    url_with_country = build_search_url("bookstore edinburgh", country="uk")
    assert "hl=en" in url_with_country
    assert "gl=uk" in url_with_country
    assert url_with_country == "https://www.google.com/maps/search/bookstore+edinburgh?hl=en&gl=uk"

    # Whitespace and uppercase handling
    url_trimmed = build_search_url("art gallery florence", country=" IT ")
    assert url_trimmed == "https://www.google.com/maps/search/art+gallery+florence?hl=en&gl=it"

def test_save_results_csv_and_json(tmp_path):
    """Verifies that save_results exports valid records to both CSV and JSON formats."""
    sample = [
        BusinessPlace(
            name="Seattle Roasters",
            category="Coffee shop",
            rating=4.8,
            reviews_count=210,
            address="100 Pine St, Seattle, WA",
            phone="+1 206-555-0123",
            website="https://seattleroasters.example.com",
            plus_code="84VV+GJ Seattle",
            latitude=47.6097,
            longitude=-122.3331,
            maps_url="https://maps.google.com/?cid=123",
            scraped_at="2026-09-23T10:00:00Z"
        )
    ]

    # Test CSV export
    csv_file = tmp_path / "results.csv"
    save_results(sample, str(csv_file))
    assert csv_file.exists()
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"] == "Seattle Roasters"
        assert rows[0]["latitude"] == "47.6097"

    # Test JSON export
    json_file = tmp_path / "results.json"
    save_results(sample, str(json_file))
    assert json_file.exists()
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "Seattle Roasters"
        assert data[0]["longitude"] == -122.3331
