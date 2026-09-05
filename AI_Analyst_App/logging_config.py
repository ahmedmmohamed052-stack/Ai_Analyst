"""
Logging setup.

Always configures structured console logging (works out of the box,
readable in `docker logs` / journalctl / any log collector).

If SENTRY_DSN is set in .env, also initializes Sentry for error tracking
and gives you alerts + stack traces for exceptions in production. Leave
it blank to skip Sentry entirely — nothing else changes.
"""
import logging
import sys

from config import LOG_LEVEL, SENTRY_DSN


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("ai_analyst")

    if SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.1)
            logger.info("Sentry error tracking enabled.")
        except ImportError:
            logger.warning(
                "SENTRY_DSN is set but the 'sentry-sdk' package isn't installed. "
                "Run: pip install sentry-sdk"
            )
    else:
        logger.info("SENTRY_DSN not set — Sentry error tracking disabled.")

    return logger


logger = setup_logging()
