from packaging.version import Version

from org.telegram.messenger import BuildVars

from .logs import _logger


def is_client_version_sufficient(version_to_compare: str) -> bool:
    try:
        return Version(BuildVars.BUILD_VERSION_STRING) >= Version(version_to_compare)
    except Exception:
        _logger.error("An error occurred:", exc_info=True)
    return False
