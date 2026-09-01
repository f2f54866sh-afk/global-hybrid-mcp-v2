import json

import pytest

from global_hybrid_v2.governance.authority import AuthorityError, AuthorityResolver


def test_unset_authority_fails_closed(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "entries": {
                    name: {"revision": "UNSET", "path": f"{name}.md"}
                    for name in ["GLOBAL", "SALES_HUMAN", "LIBRARY_FACT", "VISUAL", "EXECUTION"]
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AuthorityError):
        AuthorityResolver(path).resolve()
