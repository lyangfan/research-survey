# -*- coding: utf-8 -*-
"""ISO 3166-1 alpha-2 -> (Chinese name, English name). Extend as needed.

Data files store `country` as an ISO alpha-2 code ("US", "CN", "GB" ...). The map layer is
normalised to the same codes, so no fragile English-name matching is needed.
"""
COUNTRIES = {
    "US": ("美国", "United States"), "CN": ("中国", "China"), "GB": ("英国", "United Kingdom"),
    "CA": ("加拿大", "Canada"), "JP": ("日本", "Japan"), "KR": ("韩国", "South Korea"),
    "DE": ("德国", "Germany"), "FR": ("法国", "France"), "CH": ("瑞士", "Switzerland"),
    "NL": ("荷兰", "Netherlands"), "SE": ("瑞典", "Sweden"), "DK": ("丹麦", "Denmark"),
    "NO": ("挪威", "Norway"), "FI": ("芬兰", "Finland"), "IT": ("意大利", "Italy"),
    "ES": ("西班牙", "Spain"), "PT": ("葡萄牙", "Portugal"), "BE": ("比利时", "Belgium"),
    "AT": ("奥地利", "Austria"), "IE": ("爱尔兰", "Ireland"), "PL": ("波兰", "Poland"),
    "CZ": ("捷克", "Czechia"), "GR": ("希腊", "Greece"), "HU": ("匈牙利", "Hungary"),
    "RU": ("俄罗斯", "Russia"), "UA": ("乌克兰", "Ukraine"), "TR": ("土耳其", "Türkiye"),
    "IL": ("以色列", "Israel"), "SA": ("沙特阿拉伯", "Saudi Arabia"), "AE": ("阿联酋", "United Arab Emirates"),
    "QA": ("卡塔尔", "Qatar"), "IR": ("伊朗", "Iran"), "EG": ("埃及", "Egypt"),
    "ZA": ("南非", "South Africa"), "NG": ("尼日利亚", "Nigeria"), "KE": ("肯尼亚", "Kenya"),
    "IN": ("印度", "India"), "PK": ("巴基斯坦", "Pakistan"), "BD": ("孟加拉国", "Bangladesh"),
    "SG": ("新加坡", "Singapore"), "MY": ("马来西亚", "Malaysia"), "TH": ("泰国", "Thailand"),
    "VN": ("越南", "Vietnam"), "ID": ("印度尼西亚", "Indonesia"), "PH": ("菲律宾", "Philippines"),
    "AU": ("澳大利亚", "Australia"), "NZ": ("新西兰", "New Zealand"), "BR": ("巴西", "Brazil"),
    "MX": ("墨西哥", "Mexico"), "AR": ("阿根廷", "Argentina"), "CL": ("智利", "Chile"),
    "CO": ("哥伦比亚", "Colombia"), "HK": ("中国香港", "Hong Kong"), "TW": ("中国台湾", "Taiwan"),
    "MO": ("中国澳门", "Macao"), "EE": ("爱沙尼亚", "Estonia"), "LU": ("卢森堡", "Luxembourg"),
    "IS": ("冰岛", "Iceland"), "RO": ("罗马尼亚", "Romania"), "SI": ("斯洛文尼亚", "Slovenia"),
}


def zh(code):
    return COUNTRIES.get(code, (code, code))[0]


def en(code):
    return COUNTRIES.get(code, (code, code))[1]


# extra spellings seen in PubMed / Europe PMC / OpenAlex affiliation strings
_ALIASES = {
    "USA": "US", "U.S.A.": "US", "U.S.": "US", "United States of America": "US",
    "UK": "GB", "U.K.": "GB", "England": "GB", "Scotland": "GB", "Wales": "GB", "Northern Ireland": "GB", "Great Britain": "GB",
    "P.R. China": "CN", "PR China": "CN", "P. R. China": "CN", "People's Republic of China": "CN", "Beijing": "CN", "Shanghai": "CN",
    "Republic of Korea": "KR", "Korea": "KR", "Hong Kong SAR": "HK", "Macau": "MO", "Taiwan, ROC": "TW",
    "Czech Republic": "CZ", "Turkey": "TR", "The Netherlands": "NL", "Russian Federation": "RU", "Viet Nam": "VN", "UAE": "AE",
}
_NAMES = sorted(({en: c for c, (_, en) in COUNTRIES.items()} | _ALIASES).items(), key=lambda kv: -len(kv[0]))


def guess_country(affiliation):
    """Best-effort ISO alpha-2 code from ONE affiliation string ('' if unsure).

    Takes the country name that appears LAST in the string (affiliations end with the country),
    plus 'XX 12345' US state + ZIP. Always a hint for a human to confirm, never ground truth."""
    import re
    a = affiliation or ""
    if not a.strip():
        return ""
    best, pos = "", -1
    for name, code in _NAMES:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", a):
            if m.start() > pos:
                best, pos = code, m.start()
    if not best and re.search(r"\b[A-Z]{2}\s+\d{5}(-\d{4})?\b", a):
        best = "US"
    return best
