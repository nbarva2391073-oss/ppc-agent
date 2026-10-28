# Конфіг ASIN → клас для Brand Analytics (не за назвами). Клас "other" та SOUL уточнює Nataly.
# SQP-запит приймає список ASIN до 200 символів (≈18 ASIN) → ASIN діляться на групи.
ASIN_CLASS = {
    # ядро X2
    "B0G5QB4W6N": "core", "B0GYSB85SH": "core", "B09NBB4QP7": "core", "B0G6VRGTPR": "core",
    "B081T6QGD9": "core", "B0GYSJC1PM": "core", "B07TJW4Y94": "core", "B07PTQKZ82": "core",
    "B07ZTJM5WJ": "core", "B0GCBCW8RK": "core",
    # поза порівнянням X2
    "B0FGJST2KJ": "butterfly", "B0DHCR7D4W": "lizard",
    # потребують класифікації
    "B09RBGJYXX": "unclassified", "B0FGJVGNTK": "unclassified",
}
SQP_GROUPS = {   # група → ASIN (≤200 символів у рядку)
    "CORE":  [a for a, c in ASIN_CLASS.items() if c == "core"],
    "OTHER": [a for a, c in ASIN_CLASS.items() if c != "core"],
}
def asin_str(group): return " ".join(SQP_GROUPS[group])
assert all(len(asin_str(g)) <= 200 for g in SQP_GROUPS)
