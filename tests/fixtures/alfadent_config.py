# Safe fake configuration used only by automated CI tests.
# Real credentials are never copied into this public repository.
TELEGRAM_TOKEN = "ci-test-telegram-token"
BITRIX24_WEBHOOK_RAW = ""
BITRIX24_WEBHOOK = ""
TELEGRAM_PROXY = ""
WEBAPP_URL = "https://example.invalid/miniapp.html"

MAX_BOT_TOKEN = "ci-test-max-token"
MAX_API_BASE = "https://platform-api2.max.ru"
MAX_MINIAPP_LINK = "https://example.invalid/miniapp.html"
PROMOTIONS_URL = "https://example.invalid/assets/promotions.json"
MAX_WEBHOOK_SECRET = ""
MAX_REQUIRE_WEBHOOK_SECRET = False

INTERNAL_AUTH_SECRET = "unit-test-internal-secret"
AUTH_API_URL = "http://127.0.0.1:8001"
AUTH_DB_PATH = "/tmp/alfadent-ci/auth.sqlite3"
TELEGRAM_DATA_DIR = "/tmp/alfadent-ci/telegram"
MAX_DATA_DIR = "/tmp/alfadent-ci/max"
BITRIX_ASSIGNED_BY_ID = 33
INITDATA_MAX_AGE_SECONDS = 3600
LOG_LEVEL = "CRITICAL"
API_HOST = "127.0.0.1"
API_PORT = 8001
