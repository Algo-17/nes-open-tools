"""The helpers in server/views.py that templates call directly."""

from markupsafe import Markup, escape

from server.views import timestamp


def test_timestamp_is_a_time_element_holding_the_utc_minute():
    assert timestamp("2026-09-23T15:51:09Z") == Markup(
        '<time datetime="2026-09-23T15:51:09Z">2026-09-23 15:51 UTC</time>'
    )


def test_timestamp_survives_being_passed_into_a_string_as_a_value():
    stamp = timestamp("2026-09-23T15:51:09Z")
    assert Markup("created {}").format(stamp) == Markup("created ") + stamp
    assert escape(stamp) == stamp
