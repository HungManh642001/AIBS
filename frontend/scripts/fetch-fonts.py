#!/usr/bin/env python3
"""Tải font về repo để chạy được khi KHÔNG có internet (triển khai on-premise).

    cd frontend && python3 scripts/fetch-fonts.py

Sinh ra src/assets/fonts/*.woff2 + src/fonts.css. Chỉ giữ subset `vietnamese` và `latin` —
bỏ cyrillic/latin-ext vì giao diện thuần tiếng Việt (12 file, ~173 KB thay vì ~450 KB).

PHẢI gửi User-Agent của trình duyệt hiện đại, nếu không Google Fonts trả .ttf (nặng gấp ~3 lần)
thay vì .woff2. Và PHẢI giữ subset `vietnamese`: thiếu nó là mất sạch dấu tiếng Việt.
"""
from __future__ import annotations

import re
import pathlib
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
URL = ("https://fonts.googleapis.com/css2"
       "?family=Be+Vietnam+Pro:wght@400;500;600;700"
       "&family=IBM+Plex+Mono:wght@400;500&display=swap")
KEEP = {"vietnamese", "latin"}

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "assets" / "fonts"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    css = urllib.request.urlopen(req).read().decode("utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    faces, total = [], 0
    for subset, block in re.findall(r"/\* (\S+) \*/\s*(@font-face \{.*?\})", css, re.S):
        if subset not in KEEP:
            continue
        fam = re.search(r"font-family: '([^']+)'", block).group(1)
        wght = re.search(r"font-weight: (\d+)", block).group(1)
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        rng = re.search(r"unicode-range: ([^;]+);", block).group(1)
        name = f"{fam.lower().replace(' ', '-')}-{wght}-{subset}.woff2"
        data = urllib.request.urlopen(url).read()
        (OUT_DIR / name).write_bytes(data)
        total += len(data)
        faces.append(f"""@font-face {{
  font-family: '{fam}';
  font-style: normal;
  font-weight: {wght};
  font-display: swap;
  src: url('./assets/fonts/{name}') format('woff2');
  unicode-range: {rng};
}}""")

    (ROOT / "src" / "fonts.css").write_text(
        "/* Font tự chứa — triển khai on-premise KHÔNG có internet, dùng <link> Google Fonts thì\n"
        "   toàn bộ typography rơi về font hệ thống. Chỉ giữ subset vietnamese + latin.\n"
        "   Sinh từ Google Fonts API; muốn cập nhật thì chạy lại scripts/fetch-fonts.py. */\n\n"
        + "\n\n".join(faces) + "\n", encoding="utf-8")
    print(f"đã tải {len(faces)} file, tổng {total / 1024:.0f} KB -> {OUT_DIR}")


if __name__ == "__main__":
    main()
