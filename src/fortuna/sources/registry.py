"""Load/save the source registry and draw-source inventory."""

from pathlib import Path

from fortuna.schemas.csv_io import dump_csv, load_csv
from fortuna.schemas.sources import DrawSource, Source

SOURCE_REGISTRY = Path("metadata/source_registry.csv")
DRAW_SOURCES = Path("metadata/draw_sources.csv")


def load_source_registry(path: str | Path = SOURCE_REGISTRY) -> list[Source]:
    return load_csv(path, Source)


def save_source_registry(sources: list[Source], path: str | Path = SOURCE_REGISTRY) -> None:
    dump_csv(path, sources)


def load_draw_sources(path: str | Path = DRAW_SOURCES) -> list[DrawSource]:
    return load_csv(path, DrawSource)
