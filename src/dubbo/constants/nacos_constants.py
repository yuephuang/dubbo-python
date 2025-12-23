import os

NACOS_HOST = os.environ.get("NACOS_HOST", "")
NACOS_PORT = os.environ.get("NACOS_PORT", "")
NACOS_NAMESPACE = os.environ.get("NACOS_NAMESPACE", "")
NACOS_USERNAME = os.environ.get("NACOS_USERNAME", "")
NACOS_PASSWORD = os.environ.get("NACOS_PASSWORD", "")

NACOS_URL = os.environ.get("NACOS_URL", f"nacos://{NACOS_USERNAME}:{NACOS_PASSWORD}@{NACOS_HOST}:{NACOS_PORT}?namespace={NACOS_NAMESPACE}")

NACOS_GROUP = os.environ.get("NACOS_GROUP", "DEFAULT_GROUP")

