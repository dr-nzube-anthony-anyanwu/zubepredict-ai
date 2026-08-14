from __future__ import annotations

import asyncio

import pytest

from apps.telegram_bot.main import main


def test_aiogram_fallback_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ZUBEPREDICT_ENABLE_AIOGRAM_FALLBACK", raising=False)

    with pytest.raises(RuntimeError, match="disabled fallback"):
        asyncio.run(main())
