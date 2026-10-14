#!/usr/bin/env python3
"""Configure optimized release packaging while keeping the installed Telega Beta package ID stable."""
from pathlib import Path
import re
import sys

path = Path("TMessagesProj_App/build.gradle")
if not path.exists():
    sys.exit(f"ERROR: app Gradle file not found: {path}")
source = path.read_text(encoding="utf-8")
source = source.replace('abiFilters "armeabi-v7a", "arm64-v8a", "x86", "x86_64"',
                        'abiFilters "armeabi-v7a", "arm64-v8a"')
pattern = re.compile(r"(?ms)^        release \{\n(.*?)(?=^        \})")
build_types_start = source.find("buildTypes {")
if build_types_start < 0:
    sys.exit("ERROR: buildTypes block not found")
match = pattern.search(source, build_types_start)
if not match:
    sys.exit("ERROR: release buildType block not found")
body = match.group(1)
if 'applicationIdSuffix ".beta"' not in body:
    body = '            applicationIdSuffix ".beta"\n' + body
if "minifyEnabled true" not in body or "shrinkResources true" not in body:
    sys.exit("ERROR: release build must keep minifyEnabled and shrinkResources enabled")
source = source[:match.start(1)] + body + source[match.end(1):]
path.write_text(source, encoding="utf-8")
print("Release packaging set to arm64-v8a/armeabi-v7a, R8/minification and stable .beta package identity.")
