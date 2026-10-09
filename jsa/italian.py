"""Does a posting mention the Italian language?

For an Italian moving abroad this is the single most useful filter: a role
that asks for Italian has a shorter queue. Postings are written in the
language of the country, so the word is looked for in each of them.
"""

from __future__ import annotations

import re

ITALIAN = re.compile(
    r"\b(italian|italiano|italiana|italienisch\w*|italien|italienne|italiaans\w*|"
    r"italiensk\w*|wło(?:ski|skiego|skim)|wlo(?:ski|skiego)|italsk\w*|italština|olasz\w*)\b",
    re.I,
)


def mentions_italian(*texts: str) -> bool:
    return any(ITALIAN.search(t or "") for t in texts)
