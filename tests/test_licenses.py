"""Guard the MIT-only promise: no GPL/AGPL anywhere in the dependency tree.

Trusts OSI license classifiers (so permissively-licensed packages whose full
license *text* happens to mention "GPL" — e.g. pandas's BSD notice — are not
false-positives), and only falls back to the free-form License field when a
package ships no OSI classifier."""

import importlib.metadata as m
import re

_COPYLEFT_WORD = re.compile(r"\b(a?gpl|gnu general public|affero)\b", re.IGNORECASE)


def _is_copyleft(dist) -> bool:
    classifiers = [
        c for c in (dist.metadata.get_all("Classifier") or []) if c.startswith("License ::")
    ]
    ctext = " ".join(classifiers).lower()
    if ("general public license" in ctext or "affero" in ctext) and "lesser" not in ctext:
        return True  # an explicit (A)GPL classifier
    if classifiers:
        return False  # has OSI classifiers, none copyleft → trust them (permissive)
    lic = (dist.metadata.get("License") or "").lower()
    return bool(_COPYLEFT_WORD.search(lic)) and "lgpl" not in lic


def test_no_copyleft_in_dependency_tree():
    bad = sorted({d.metadata["Name"] for d in m.distributions() if _is_copyleft(d)})
    assert not bad, f"copyleft dependency detected: {bad}"
