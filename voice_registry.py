import re

VOICE_MARKER_PATTERN = re.compile(r"^\s*<<VOICE:\s*([^>]+?)\s*>>\s*", re.IGNORECASE)

VOICE_CATALOG = {
    "james": {
        "name": "James",
        "voice_id": "EkK5I93UQWFDigLMpZcX",
        "description": "Husky, older male voice with an imposing, masculine main-character vibe.",
        "gender": "male",
    },
    "ellen": {
        "name": "Ellen",
        "voice_id": "BIvP0GN1cAtSRTxNHnWS",
        "description": "Calm, normal young-adult woman voice.",
        "gender": "female",
    },
    "mark": {
        "name": "Mark",
        "voice_id": "5F6a8n4ijdCrImoXgxM9",
        "description": "Normal adult male voice, good for regular story narration.",
        "gender": "male",
    },
    "adam": {
        "name": "Adam",
        "voice_id": "s3TPKV1kjDlVtZbl4Ksh",
        "description": "Soft male voice with a gentler, lighter tone.",
        "gender": "male",
    },
    "vincent": {
        "name": "Vincent",
        "voice_id": "Qe9WSybioZxssVEwlBSo",
        "description": "Deep, soothing male voice with a strong horror-supporting tone.",
        "gender": "male",
    },
    "hope": {
        "name": "Hope",
        "voice_id": "WAhoMTNdLdMoq1j3wf3I",
        "description": "Young, lovely, flirty woman voice.",
        "gender": "female",
    },
    "jessica": {
        "name": "Jessica",
        "voice_id": "lxYfHSkYm1EzQzGhdbfc",
        "description": "Strong default woman voice for story reading.",
        "gender": "female",
    },
    "oxley": {
        "name": "Oxley",
        "voice_id": "iUqOXhMfiOIbBejNtfLR",
        "description": "Older gentleman voice, warm and advice-friendly like a young grandpa.",
        "gender": "male",
    },
    "carol": {
        "name": "Carol",
        "voice_id": "5u41aNhyCU6hXOcjPPv0",
        "description": "Older woman voice with a warm, young-grandma energy.",
        "gender": "female",
    },
    "serena": {
        "name": "Serena",
        "voice_id": "RGb96Dcl0k5eVje8EBch",
        "description": "Warm, supportive woman voice with a coach or sisterhood feel.",
        "gender": "female",
    },
    "nathaniel": {
        "name": "Nathaniel",
        "voice_id": "AeRdCCKzvd23BpJoofzx",
        "description": "Engaging, suspense-driven male voice and the best default for horror narration.",
        "gender": "male",
    },
    "myriam": {
        "name": "Myriam",
        "voice_id": "H8BjWxFjrzNszTO74noq",
        "description": "Girl child voice.",
        "gender": "female",
    },
    "kiran": {
        "name": "Kiran",
        "voice_id": "o80picuztV1xYiPeIrpa",
        "description": "Boy child voice.",
        "gender": "male",
    },
}

CATEGORY_DEFAULT_VOICE_NAMES = {
    "story": {
        "female": "Jessica",
        "male": "Mark",
    },
    "horror": {
        "female": "Ellen",
        "male": "Nathaniel",
    },
    "ask": {
        "female": "Ellen",
        "male": "Mark",
    },
}


def normalize_voice_name(name):
    return str(name or "").strip().lower()


def get_voice_entry(name):
    return VOICE_CATALOG.get(normalize_voice_name(name))


def build_voice_catalog_prompt():
    lines = []
    for entry in VOICE_CATALOG.values():
        lines.append(f"- {entry['name']}: {entry['description']}")
    return "\n".join(lines)


def default_voice_name_for(category="story", voice_gender="female"):
    category_defaults = CATEGORY_DEFAULT_VOICE_NAMES.get(
        str(category or "").strip().lower(),
        CATEGORY_DEFAULT_VOICE_NAMES["story"],
    )
    return category_defaults.get(voice_gender or "female") or category_defaults["female"]


def voice_id_for_name(name, category="story", voice_gender="female"):
    entry = get_voice_entry(name)
    if entry:
        return entry["voice_id"], entry["name"]

    fallback_name = default_voice_name_for(category=category, voice_gender=voice_gender)
    fallback_entry = get_voice_entry(fallback_name)
    return fallback_entry["voice_id"], fallback_entry["name"]


def strip_voice_marker(text):
    raw_text = str(text or "")
    match = VOICE_MARKER_PATTERN.match(raw_text)
    if not match:
        return None, raw_text.strip()
    voice_name = match.group(1).strip()
    stripped_text = raw_text[match.end() :].strip()
    return voice_name or None, stripped_text
