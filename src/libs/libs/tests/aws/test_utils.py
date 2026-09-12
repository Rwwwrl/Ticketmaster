from libs.aws.utils import build_s3_object_public_url


def test_build_s3_object_public_url_returns_virtual_hosted_style_url() -> None:
    url = build_s3_object_public_url(
        region="eu-central-1", bucket="ticketmaster-test-eu-media-public", key="event-trailer/a.mp4"
    )

    assert url == "https://ticketmaster-test-eu-media-public.s3.eu-central-1.amazonaws.com/event-trailer/a.mp4"
