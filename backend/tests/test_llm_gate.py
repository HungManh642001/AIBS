"""Trần song song cho MỌI call LLM — một cổng chung, tạo theo event loop đang chạy."""
import asyncio

import config
from services import llm_gate


def _dat_tran(monkeypatch, n: int) -> None:
    monkeypatch.setenv("ABES_AI_SONG_SONG", str(n))
    config.get_settings.cache_clear()


async def test_cong_chan_dung_tran(monkeypatch):
    """Dựng 10 việc nhưng trần 2 -> đỉnh đồng thời không bao giờ vượt 2."""
    _dat_tran(monkeypatch, 2)
    dang_bay = 0
    dinh = 0

    async def viec():
        nonlocal dang_bay, dinh
        async with llm_gate.cong():
            dang_bay += 1
            dinh = max(dinh, dang_bay)
            await asyncio.sleep(0.01)
            dang_bay -= 1

    await asyncio.gather(*(viec() for _ in range(10)))
    assert dinh == 2


async def test_cong_cho_phep_song_song_that(monkeypatch):
    """Trần rộng -> nhiều việc chạy chồng nhau (nếu không, gate đang tuần tự hoá oan)."""
    _dat_tran(monkeypatch, 8)
    dang_bay = 0
    dinh = 0

    async def viec():
        nonlocal dang_bay, dinh
        async with llm_gate.cong():
            dang_bay += 1
            dinh = max(dinh, dang_bay)
            await asyncio.sleep(0.01)
            dang_bay -= 1

    await asyncio.gather(*(viec() for _ in range(8)))
    assert dinh == 8


async def test_cong_dung_lai_trong_cung_mot_loop(monkeypatch):
    _dat_tran(monkeypatch, 3)
    assert llm_gate.cong() is llm_gate.cong()


def test_cong_khong_dinh_vao_loop_cu(monkeypatch):
    """Semaphore gắn vào loop ở lần dùng đầu; dùng lại qua loop khác sẽ nổ 'bound to a
    different event loop'. Mỗi loop phải có cổng riêng."""
    _dat_tran(monkeypatch, 2)

    async def lay():
        async with llm_gate.cong():
            return llm_gate.cong()

    a = asyncio.run(lay())
    b = asyncio.run(lay())
    assert a is not b
