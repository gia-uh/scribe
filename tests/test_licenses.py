"""Guard the MIT-only promise: no GPL/AGPL anywhere in the dependency tree."""

import importlib.metadata as m


def test_no_copyleft_in_dependency_tree():
    bad = []
    for d in m.distributions():
        name = d.metadata["Name"]
        blob = d.metadata.get("License") or ""
        blob += " " + " ".join(d.metadata.get_all("Classifier") or [])
        low = blob.lower()
        # LGPL is permissive enough for dynamic linking; (A)GPL is not.
        if "gpl" in low and "lgpl" not in low.replace("agpl", ""):
            bad.append(name)
    assert not bad, f"copyleft dependency detected: {sorted(set(bad))}"
