"""Trần song song cho MỌI call LLM — một cổng CHUNG cho mọi đường gọi.

Vì sao một cổng chung chứ không phải mỗi tầng một cái: bước chấm lồng gather trong gather (tiêu
chí × nội dung) và ingest gather theo trang. Nếu mỗi tầng tự giới hạn thì TÍCH các trần mới là số
request thật dội xuống proxy — vượt xa sức chứa mà không ai chủ ý.

Semaphore tạo theo EVENT LOOP đang chạy, không phải một biến ở mức module: Python 3.11 gắn
Semaphore vào loop ở lần dùng đầu tiên, nên một biến dùng chung qua nhiều loop (pytest tạo loop
mới mỗi test) sẽ nổ "bound to a different event loop".
"""
from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from config import get_settings

_cong_theo_loop: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    WeakKeyDictionary())


def cong() -> asyncio.Semaphore:
    """Semaphore của event loop đang chạy. Trần đọc từ `Settings.ai_song_song` lần đầu mỗi loop."""
    loop = asyncio.get_running_loop()
    sem = _cong_theo_loop.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, get_settings().ai_song_song))
        _cong_theo_loop[loop] = sem
    return sem
