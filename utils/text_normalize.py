import re


def normalize_text(text: str) -> str:
    # Basic cleanup: collapse whitespace and fix common ASR artifacts.
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        " milligram ": " mg ",
        " milligrams ": " mg ",
        " milliliter ": " ml ",
        " milliliters ": " ml ",
        " microgram ": " mcg ",
        " micrograms ": " mcg ",
        " twice daily ": " BID ",
        " three times daily ": " TID ",
        " four times daily ": " QID ",
        " once daily ": " daily ",
        " by mouth ": " orally ",
    }
    normalized = f" {text} "
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    text = normalized.strip()
    return text
