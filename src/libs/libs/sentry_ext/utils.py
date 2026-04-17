import sentry_sdk

from libs.sentry_ext.settings import SentrySettingsMixin


def setup_sentry(settings: SentrySettingsMixin, release: str) -> None:
    if settings.sentry_dsn is None:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment.value,
        release=release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=settings.sentry_send_pii,
    )
