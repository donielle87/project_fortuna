"""Per-game YAML config loader (config/games/*.yaml).

Config files reference regime metadata rather than duplicating constants —
the matrix of record lives in metadata/game_regimes.csv.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CONFIG_GAMES_DIR = Path("config/games")


class GameConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: str
    name: str
    operator: str
    current_regime_id: str
    current_statistical_regime_id: str
    draw_source_ids: list[str] = []
    notes: str | None = None


def load_game_config(path: str | Path) -> GameConfig:
    with Path(path).open(encoding="utf-8") as fh:
        return GameConfig.model_validate(yaml.safe_load(fh))


def load_all_game_configs(
    config_dir: str | Path = CONFIG_GAMES_DIR,
) -> dict[str, GameConfig]:
    configs: dict[str, GameConfig] = {}
    for path in sorted(Path(config_dir).glob("*.yaml")):
        cfg = load_game_config(path)
        configs[cfg.game_id] = cfg
    return configs
