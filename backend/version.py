from pathlib import Path


APP_VERSION = "1.0.0"
BUILD_INFO_PATH = Path(__file__).resolve().parents[1] / ".build-info"


def load_build_info(path: Path = BUILD_INFO_PATH) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    build_info: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        build_info[key.strip()] = value.strip()

    return build_info
