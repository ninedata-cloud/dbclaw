#!/usr/bin/env python3
"""Validate bilingual built-in documents and skill metadata."""
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.builtin_docs.english_docs import ENGLISH_DOCS_MAP  # noqa: E402
from backend.services.builtin_docs.seeder import DOCS_MAP, SCENARIO_CODES  # noqa: E402
from backend.skills.loader import SkillLoader  # noqa: E402

HAN = re.compile(r"[\u3400-\u9fff]")
errors: list[str] = []

for db_type, chinese_docs in DOCS_MAP.items():
    english_docs = ENGLISH_DOCS_MAP.get(db_type, [])
    if len(english_docs) != len(chinese_docs):
        errors.append(f"{db_type}: {len(chinese_docs)} Chinese docs but {len(english_docs)} English docs")
        continue
    for index, (chinese, english) in enumerate(zip(chinese_docs, english_docs)):
        scenario_code = english.get("category_code")
        if scenario_code != SCENARIO_CODES.get(chinese.get("category")):
            errors.append(f"{db_type}[{index}]: scenario mismatch")
        if HAN.search(english.get("title", "")) or HAN.search(english.get("content", "")):
            errors.append(f"{db_type}[{index}]: English document contains Han characters")
        if len(english.get("content", "")) < 800:
            errors.append(f"{db_type}[{index}]: English document is incomplete")

skill_files = sorted((ROOT / "backend" / "skills" / "builtin").glob("*.yaml"))
for skill_file in skill_files:
    try:
        definition = SkillLoader.load_from_yaml(skill_file.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{skill_file.name}: cannot load ({exc})")
        continue
    if set(definition.i18n) != {"zh-CN", "en-US"}:
        errors.append(f"{skill_file.name}: requires exactly zh-CN and en-US metadata")
        continue
    parameter_names = {parameter.name for parameter in definition.parameters}
    permission_names = set(definition.permissions)
    for locale, translation in definition.i18n.items():
        if not translation.name.strip() or not translation.description.strip():
            errors.append(f"{skill_file.name}: blank {locale} name or description")
        if set(translation.parameter_descriptions) != parameter_names:
            errors.append(f"{skill_file.name}: incomplete {locale} parameter descriptions")
        if set(translation.permission_descriptions) != permission_names:
            errors.append(f"{skill_file.name}: incomplete {locale} permission descriptions")
    english = definition.i18n["en-US"]
    if HAN.search(english.name) or HAN.search(english.description):
        errors.append(f"{skill_file.name}: English metadata contains Han characters")

if errors:
    print("Built-in i18n content audit failed:", file=sys.stderr)
    for error in errors[:100]:
        print(f"  {error}", file=sys.stderr)
    raise SystemExit(1)

print(f"Built-in i18n content audit passed ({sum(map(len, DOCS_MAP.values()))} document groups, {len(skill_files)} skills).")
