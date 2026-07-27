from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def default_data_dir() -> Path:
    override = os.getenv("TAIYI_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Taiyi"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "taiyi"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    provider: str = "mock"
    openai_model: str = "gpt-5.6-terra"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "taiyi.sqlite3"

    @classmethod
    def load(cls, data_dir: Path | None = None) -> Settings:
        return cls(
            data_dir=(data_dir or default_data_dir()).resolve(),
            provider=os.getenv("TAIYI_PROVIDER", "mock").lower(),
            openai_model=os.getenv("TAIYI_OPENAI_MODEL", "gpt-5.6-terra"),
        )
