"""Simple manual test for VA-6754: Sentry events with service_debug=True vs False."""

import sentry_sdk
import structlog

from microbootstrap import InstrumentsSetupperSettings
from microbootstrap.instruments_setupper import InstrumentsSetupper
from sentry_sdk.integrations.logging import LoggingIntegration

# Change this to test both modes
SERVICE_DEBUG = False  # Set to False to test production mode

settings = InstrumentsSetupperSettings(
    service_debug=SERVICE_DEBUG,
    # sentry_dsn="YOUR_DSN_HERE",  # Replace with real DSN
    # logging_log_level=10,  # DEBUG
)

setupper = InstrumentsSetupper(settings)
setupper.setup()

logger = structlog.get_logger()

# Test 1: Log error via structlog
for one in range(10):
    logger.error("test_error_from_structlog", key="value", service_debug=SERVICE_DEBUG)
# # Test 2: Capture exception directly
# try:
#     raise ValueError("test_exception_direct")
# except ValueError:
#     sentry_sdk.capture_exception()

# # Test 3: Log exception via structlog
# try:
#     raise RuntimeError("test_exception_structlog")
# except RuntimeError:
#     logger.exception("caught_exception")

# print(f"\nDone. Check Sentry for events. service_debug={SERVICE_DEBUG}")
