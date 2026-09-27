from libs.aws.utils import build_cdn_object_url


def test_build_cdn_object_url_returns_url_under_cdn_domain() -> None:
    url = build_cdn_object_url(domain="media.test-eu.as-ticketmaster.com", key="event-trailer/a.mp4")

    assert url == "https://media.test-eu.as-ticketmaster.com/event-trailer/a.mp4"
