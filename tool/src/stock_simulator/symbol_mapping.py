from __future__ import annotations

import csv
from pathlib import Path


class UnknownSymbolMappingError(ValueError):
    pass


class SymbolMapper:
    def __init__(self, mappings: dict[tuple[str, str], str]):
        self._mappings = dict(mappings)
        destinations = {}
        for (source, source_symbol), symbol in self._mappings.items():
            destination = (source, symbol)
            existing_source_symbol = destinations.get(destination)
            if (
                existing_source_symbol is not None
                and existing_source_symbol != source_symbol
            ):
                raise ValueError(
                    f"{source_symbol} and {existing_source_symbol} both map "
                    f"to {source} / {symbol}"
                )
            destinations[destination] = source_symbol

    @classmethod
    def from_csv(cls, path: str | Path) -> SymbolMapper:
        mappings = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            required = {"source", "source_symbol", "symbol"}
            headers = set(reader.fieldnames or [])
            missing = required - headers
            if missing:
                raise ValueError(
                    f"Missing symbol mapping columns: {', '.join(sorted(missing))}"
                )

            for line, row in enumerate(reader, start=2):
                source = (row.get("source") or "").strip()
                source_symbol = (row.get("source_symbol") or "").strip()
                symbol = (row.get("symbol") or "").strip()
                if not source or not source_symbol or not symbol:
                    raise ValueError(f"line {line}: mapping values must not be empty")
                key = (source, source_symbol)
                if key in mappings:
                    raise ValueError(
                        f"line {line}: duplicate mapping for "
                        f"{source} / {source_symbol}"
                    )
                mappings[key] = symbol
        return cls(mappings)

    def lookup(self, source: str, source_symbol: str) -> str | None:
        return self._mappings.get((source, source_symbol))

    def resolve(self, source: str, source_symbol: str) -> str:
        symbol = self.lookup(source, source_symbol)
        if symbol is None:
            raise UnknownSymbolMappingError(
                f"No internal symbol mapping for {source} / {source_symbol}"
            )
        return symbol
