import re


# Exact Reddit shorthand replacements applied before the OpenAI polish step.
# Add new entries here when a phrase sounds awkward in TTS.
VOCAB_REPLACEMENTS = {
    "AITAH": "Am I the asshole",
    "AITA": "Am I the asshole",
    "WIBTAH": "Would I be the asshole",
    "WIBTA": "Would I be the asshole",
    "TLDR": "Too long, didn't read",
    "TL;DR": "Too long, didn't read",
    "TL:DR": "Too long, didn't read",
    "TL/DR": "Too long, didn't read",
    "bc": "because",
    "b/c": "because",
    "w/": "with",
    "w/o": "without",
    "idk": "I don't know",
    "imo": "in my opinion",
    "imho": "in my honest opinion",
}


def normalize_reddit_vocabulary(text, replacements=None):
    """
    Replace known Reddit shorthand only when it appears as its own token.
    """
    if not text:
        return text

    active_replacements = replacements or VOCAB_REPLACEMENTS
    normalized = text

    for source, replacement in sorted(
        active_replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])",
            flags=re.IGNORECASE,
        )
        normalized = pattern.sub(replacement, normalized)

    return normalized
