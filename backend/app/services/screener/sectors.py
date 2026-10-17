"""Static sector -> screener.in URL mapping.

This mirrors the sectors the original analysis notebook covered. It is plain
Python today; if the catalogue needs to be user-editable later it can move to
a database table behind the same list_sectors()/get_sector_url() functions
without touching any of the calling code.
"""

from app.exceptions import SectorNotFoundError

SECTOR_MAP: dict[str, str] = {
    "IT": "https://www.screener.in/market/IN08/IN0801/IN080101/",
    "IT_small": "https://www.screener.in/market/IN08/IN0801/IN080101/?page=2",
    "IT_enabled_service": "https://www.screener.in/market/IN08/IN0801/IN080102/IN080102001/",
    "consumer_durablity": "https://www.screener.in/market/IN02/IN0202/IN020201/",
    "Gems_Jewellery": "https://www.screener.in/market/IN02/IN0202/IN020201/IN020201005/",
    "Defense": "https://www.screener.in/market/IN07/IN0702/IN070201/IN070201001/",
    "Residential_Commercial_project": "https://www.screener.in/market/IN02/IN0205/IN020501/IN020501001/",
    "phara": "https://www.screener.in/market/IN06/IN0601/IN060101/",
    "pharma_small": "https://www.screener.in/market/IN06/IN0601/IN060101/IN060101001/?page=2",
    "textiles": "https://www.screener.in/market/IN02/IN0203/IN020301/",
    "hospital": "https://www.screener.in/market/IN06/IN0601/IN060103/IN060103001/",
    "consumer_electronic": "https://www.screener.in/market/IN02/IN0202/IN020201/IN020201003/",
    "industrial_product": "https://www.screener.in/market/IN07/IN0702/IN070204/IN070204008/",
    "hotels": "https://www.screener.in/market/IN02/IN0206/IN020601/IN020601001/",
    "It_enabled": "https://www.screener.in/market/IN08/IN0801/IN080102/IN080102001/",
    "Com_hardware": "https://www.screener.in/market/IN08/IN0801/IN080103/IN080103001/",
    "NBFC": "https://www.screener.in/market/IN05/IN0501/IN050101/IN050101004/?limit=50&page=1",
    "Auto_component": "https://www.screener.in/market/IN02/IN0201/IN020102/IN020102001/?limit=100&page=1",
    "Bank": "https://www.screener.in/market/IN05/IN0501/IN050102/?limit=50&page=1",
    "Electrical_Equipment": "https://www.screener.in/market/IN07/IN0702/IN070203/IN070203002/?limit=50&page=1",
    "Power_Generation": "https://www.screener.in/market/IN11/IN1101/IN110101/IN110101004/",
    "FMCG": "https://www.screener.in/market/IN04/IN0401/?page=1",
    "FMCG_SMALL": "https://www.screener.in/market/IN04/IN0401/?page=2",
    "Specialty_Chemicals": "https://www.screener.in/market/IN01/IN0101/IN010101/IN010101002/",
}


def get_sector_url(sector_key: str) -> str:
    try:
        return SECTOR_MAP[sector_key]
    except KeyError as exc:
        raise SectorNotFoundError(f"Unknown sector key '{sector_key}'") from exc


def get_sector_label(sector_key: str) -> str:
    if sector_key not in SECTOR_MAP:
        raise SectorNotFoundError(f"Unknown sector key '{sector_key}'")
    # Keep existing acronyms (IT, NBFC, FMCG, ...) shouted instead of title-casing them away.
    words = sector_key.split("_")
    return " ".join(word if word.isupper() else word.capitalize() for word in words if word)


def list_sectors() -> list[dict]:
    return [{"key": key, "label": get_sector_label(key)} for key in SECTOR_MAP]
