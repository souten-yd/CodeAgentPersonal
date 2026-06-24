"""Contract tests for SEARCH/REPLACE edit-block parsing (weak-model edit format)."""
from __future__ import annotations

from agent.atlas_edit_format import (
    harvest_search_replace_edits,
    parse_search_replace_blocks,
)

ONE_BLOCK = """js/main.js
<<<<<<< SEARCH
const renderer = new Renderer(canvas.getContext('2d'));
=======
const engine = new GameEngine();
>>>>>>> REPLACE
"""

TWO_BLOCKS = """<<<<<<< SEARCH
a = 1;
=======
a = 2;
>>>>>>> REPLACE
some prose
<<<<<<< SEARCH
b = 3;
=======
b = 4;
>>>>>>> REPLACE
"""


def test_single_block_with_path_line():
    edits = parse_search_replace_blocks(ONE_BLOCK)
    assert len(edits) == 1
    e = edits[0]
    assert e["path"] == "js/main.js"
    assert e["old_string"] == "const renderer = new Renderer(canvas.getContext('2d'));"
    assert e["new_string"] == "const engine = new GameEngine();"


def test_default_path_used_when_no_path_line():
    edits = parse_search_replace_blocks(TWO_BLOCKS, default_path="js/main.js")
    assert len(edits) == 2
    assert all(e["path"] == "js/main.js" for e in edits)
    assert edits[0]["old_string"] == "a = 1;" and edits[0]["new_string"] == "a = 2;"
    assert edits[1]["new_string"] == "b = 4;"


def test_block_without_resolvable_path_is_dropped():
    edits = parse_search_replace_blocks(TWO_BLOCKS)  # no path line, no default
    assert edits == []


def test_tolerant_marker_lengths_and_fenced():
    text = """```js
app.js
<<<<< SEARCH
x
==========
y
>>>>> REPLACE
```"""
    edits = parse_search_replace_blocks(text)
    assert len(edits) == 1
    assert edits[0]["path"] == "app.js"
    assert edits[0]["old_string"] == "x" and edits[0]["new_string"] == "y"


def test_deletion_block_empty_replacement():
    text = "a.js\n<<<<<<< SEARCH\ndead = true;\n=======\n\n>>>>>>> REPLACE\n"
    edits = parse_search_replace_blocks(text)
    assert len(edits) == 1
    assert edits[0]["old_string"] == "dead = true;"
    assert edits[0]["new_string"] == ""


def test_no_markers_returns_empty():
    assert parse_search_replace_blocks("just some code\nconst x = 1;") == []
    assert parse_search_replace_blocks("") == []


def test_harvest_from_search_replace_field():
    out = {"search_replace": ONE_BLOCK}
    edits = harvest_search_replace_edits(out, default_path="js/main.js")
    assert len(edits) == 1 and edits[0]["path"] == "js/main.js"


def test_harvest_from_proposed_content_field():
    out = {"proposed_content": TWO_BLOCKS}
    edits = harvest_search_replace_edits(out, default_path="js/main.js")
    assert len(edits) == 2


def test_harvest_returns_empty_when_no_blocks():
    out = {"proposed_content": "const x = 1;\nfunction f(){}"}
    assert harvest_search_replace_edits(out) == []
