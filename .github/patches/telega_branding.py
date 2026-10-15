#!/usr/bin/env python3
"""Replace visible Telegram branding in Android resources and UI text with Telega."""
from pathlib import Path
import re
import sys

RES = Path("TMessagesProj/src/main/res")
JAVA = Path("TMessagesProj/src/main/java")
if not RES.exists() or not JAVA.exists():
    print("ERROR: Android source/resources directory missing", file=sys.stderr)
    sys.exit(1)

URL_OR_EMAIL = re.compile(r"(?:https?://[^\s\"<>]+|tg://[^\s\"<>]+|mailto:[^\s\"<>]+|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.I)

def replace_visible(text):
    pieces = URL_OR_EMAIL.split(text)
    matches = URL_OR_EMAIL.findall(text)
    # re.split drops the separators, so rebuild while keeping URLs and email intact.
    tokens = []
    last = 0
    for match in URL_OR_EMAIL.finditer(text):
        tokens.append(replace_words(text[last:match.start()]))
        tokens.append(match.group(0))
        last = match.end()
    tokens.append(replace_words(text[last:]))
    return "".join(tokens)

def replace_words(text):
    text = re.sub(r"(?<![A-Za-z])Telegram Beta(?![A-Za-z])", "Telega Beta", text, flags=re.I)
    return re.sub(r"(?<![A-Za-z])Telegram(?![A-Za-z])", "Telega", text, flags=re.I)

changed_resources = 0
visible_xml_attribute = re.compile(r'(?P<name>(?:android:)?(?:label|title|text|contentDescription|summary|hint|description|tooltipText|accessibilityText))\s*=\s*"(?P<value>[^"]*)"', re.I)
for path in RES.rglob("*.xml"):
    source = path.read_text(encoding="utf-8")
    original = source
    source = re.sub(r">([^<>]*)<", lambda m: ">" + replace_visible(m.group(1)) + "<", source)
    def update_xml_attribute(match):
        value = match.group("value")
        if value.startswith(("@", "?")):
            return match.group(0)
        return match.group("name") + '="' + replace_visible(value) + '"'
    source = visible_xml_attribute.sub(update_xml_attribute, source)
    if source != original:
        path.write_text(source, encoding="utf-8")
        changed_resources += 1

changed_java = 0
literal = re.compile(r'"(?:\\.|[^"\\])*"')
for path in JAVA.rglob("*.java"):
    # Package/model/TL protocol source is deliberately excluded; branding is UI-only.
    if "/tgnet/" in path.as_posix() or "/TLRPC" in path.as_posix():
        continue
    source = path.read_text(encoding="utf-8")
    original = source
    def update_literal(match):
        raw = match.group(0)
        inner = raw[1:-1]
        replaced = replace_visible(inner)
        return '"' + replaced + '"'
    source = literal.sub(update_literal, source)
    if source != original:
        path.write_text(source, encoding="utf-8")
        changed_java += 1

if changed_resources == 0 and changed_java == 0:
    print("ERROR: no visible Telegram branding anchors found in upstream source", file=sys.stderr)
    sys.exit(1)
print(f"Telega branding updated in {changed_resources} XML resource files and {changed_java} UI/source files.")
