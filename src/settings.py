import os
import sys

# Application Metadata
BUILD_VERSION = "1.0.0"
CLI_VERSION = "1.1.7"
RELEASE_CHANNEL = "stable"
# Application Settings
APP_NAME = "YASB"
APP_NAME_FULL = "YASB Yike"
APP_BAR_TITLE = "YasbBar"
APP_ID = "shuf.YASBYike"
IS_FROZEN = getattr(sys, "frozen", False)
SCRIPT_PATH = os.path.dirname(sys.executable) if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))
# URLs
GITHUB_URL = "https://github.com/uitTe/yike_yasb"
GITHUB_DOCS_URL = f"{GITHUB_URL}/tree/main/docs"
# Configuration Settings
DEFAULT_CONFIG_DIRECTORY = os.path.join(SCRIPT_PATH, "defaults")
DEFAULT_STYLES_FILENAME = "styles.css"
DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_LOG_FILENAME = "yasb.log"
