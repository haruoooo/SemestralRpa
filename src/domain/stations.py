"""Reference list of boarding stations per line (RN05). MVP scope: Lines 1-Azul and 3-Vermelha."""

from src.domain.lineStatus import normalizeText

STATIONS_BY_LINE: dict[int, tuple[str, ...]] = {
    1: (
        "Tucuruvi", "Parada Inglesa", "Jardim São Paulo-Ayrton Senna", "Santana", "Carandiru",
        "Portuguesa-Tietê", "Armênia", "Tiradentes", "Luz", "São Bento", "Sé", "Japão-Liberdade",
        "São Joaquim", "Vergueiro", "Paraíso", "Ana Rosa", "Vila Mariana", "Santa Cruz",
        "Praça da Árvore", "Saúde", "São Judas", "Conceição", "Jabaquara",
    ),
    3: (
        "Palmeiras-Barra Funda", "Marechal Deodoro", "Santa Cecília", "República", "Anhangabaú", "Sé",
        "Pedro II", "Brás", "Bresser-Mooca", "Belém", "Tatuapé", "Carrão", "Penha", "Vila Matilde",
        "Guilhermina-Esperança", "Patriarca-Vila Ré", "Artur Alvim", "Corinthians-Itaquera",
    ),
}

SUPPORTED_LINES = tuple(sorted(STATIONS_BY_LINE))


def _key(name: str) -> str:
    return " ".join(normalizeText(name).replace("–", "-").replace(" - ", "-").split())


_INDEX: dict[int, dict[str, str]] = {line: {_key(name): name for name in names} for line, names in STATIONS_BY_LINE.items()}


def findStation(name: str, lineNumber: int) -> str | None:
    """Canonical station name if it belongs to the line (accent and case insensitive), else None."""
    return _INDEX.get(lineNumber, {}).get(_key(name))


def linesOfStation(name: str) -> list[int]:
    return [line for line, index in _INDEX.items() if _key(name) in index]
