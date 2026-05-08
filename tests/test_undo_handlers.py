"""Tests for undo / redo / get_undo_history handlers.

Depends on test_server_commands.py to inject the hou mock into sys.modules.
Run via `pytest tests/` (full suite). Standalone run is unsupported.
"""
import sys
import pytest

if "hou" not in sys.modules:
    pytest.skip(
        "Requires hou mock from test_server_commands.py — run via `pytest tests/`",
        allow_module_level=True,
    )

# hou is now in sys.modules; safe to import the handler module.
from houdinimcp.handlers.undo import undo, redo, get_undo_history


class _UndoStackMock:
    """Stand-in for hou.undos. Maintains newest-first stacks consistent with the API."""

    class _Group:
        def __init__(self, label):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []
        self.fail_next_undo = False
        self.fail_next_redo = False

    def group(self, label):
        return self._Group(label)

    def undoLabels(self):
        return list(self.undo_stack)

    def redoLabels(self):
        return list(self.redo_stack)

    def performUndo(self):
        if self.fail_next_undo:
            self.fail_next_undo = False
            raise sys.modules["hou"].OperationFailed("simulated")
        if not self.undo_stack:
            raise sys.modules["hou"].OperationFailed("nothing to undo")
        self.redo_stack.insert(0, self.undo_stack.pop(0))

    def performRedo(self):
        if self.fail_next_redo:
            self.fail_next_redo = False
            raise sys.modules["hou"].OperationFailed("simulated")
        if not self.redo_stack:
            raise sys.modules["hou"].OperationFailed("nothing to redo")
        self.undo_stack.insert(0, self.redo_stack.pop(0))


@pytest.fixture
def undo_mock():
    """Replace hou.undos with a fresh _UndoStackMock; restore on teardown."""
    hou = sys.modules["hou"]
    original = hou.undos
    mock = _UndoStackMock()
    hou.undos = mock
    yield mock
    hou.undos = original


# ---------- undo ----------

class TestUndo:
    def test_empty_stack_returns_dict(self, undo_mock):
        result = undo()
        assert result == {"performed": False, "reason": "undo stack empty"}

    def test_normal_undo_pops_top(self, undo_mock):
        undo_mock.undo_stack = ["MCP: create_node"]
        result = undo()
        assert result == {"performed": True, "undone_label": "MCP: create_node"}
        assert undo_mock.undo_stack == []
        assert undo_mock.redo_stack == ["MCP: create_node"]

    def test_undo_returns_top_label_when_multiple(self, undo_mock):
        undo_mock.undo_stack = ["MCP: newest", "MCP: middle", "MCP: oldest"]
        result = undo()
        assert result["performed"] is True
        assert result["undone_label"] == "MCP: newest"
        assert undo_mock.undo_stack == ["MCP: middle", "MCP: oldest"]
        assert undo_mock.redo_stack == ["MCP: newest"]

    def test_operation_failed_returns_dict(self, undo_mock):
        undo_mock.undo_stack = ["MCP: x"]
        undo_mock.fail_next_undo = True
        result = undo()
        assert result["performed"] is False
        assert "performUndo failed" in result["reason"]


# ---------- redo ----------

class TestRedo:
    def test_empty_stack_returns_dict(self, undo_mock):
        result = redo()
        assert result == {"performed": False, "reason": "redo stack empty"}

    def test_normal_redo_pops_top(self, undo_mock):
        undo_mock.redo_stack = ["MCP: create_node"]
        result = redo()
        assert result == {"performed": True, "redone_label": "MCP: create_node"}
        assert undo_mock.redo_stack == []
        assert undo_mock.undo_stack == ["MCP: create_node"]

    def test_operation_failed_returns_dict(self, undo_mock):
        undo_mock.redo_stack = ["MCP: x"]
        undo_mock.fail_next_redo = True
        result = redo()
        assert result["performed"] is False
        assert "performRedo failed" in result["reason"]


# ---------- get_undo_history ----------

class TestGetUndoHistory:
    def test_empty_stacks(self, undo_mock):
        result = get_undo_history()
        assert result == {
            "undo_stack": [],
            "redo_stack": [],
            "undo_total": 0,
            "redo_total": 0,
            "current_head_label": None,
        }

    def test_preserves_newest_first_order(self, undo_mock):
        undo_mock.undo_stack = ["MCP: newest", "MCP: middle", "MCP: oldest"]
        result = get_undo_history()
        assert result["undo_stack"] == ["MCP: newest", "MCP: middle", "MCP: oldest"]
        assert result["current_head_label"] == "MCP: newest"
        assert result["undo_total"] == 3

    def test_limit_truncates(self, undo_mock):
        undo_mock.undo_stack = [f"MCP: op{i}" for i in range(50)]
        result = get_undo_history(limit=5)
        assert result["undo_stack"] == [f"MCP: op{i}" for i in range(5)]
        assert result["undo_total"] == 50
        assert result["current_head_label"] == "MCP: op0"

    def test_redo_stack_returned(self, undo_mock):
        undo_mock.redo_stack = ["MCP: x", "MCP: y"]
        result = get_undo_history()
        assert result["redo_stack"] == ["MCP: x", "MCP: y"]
        assert result["redo_total"] == 2

    @pytest.mark.parametrize("bad_limit", [0, -1, 201, "20", True])
    def test_invalid_limit_raises_value_error(self, undo_mock, bad_limit):
        with pytest.raises(ValueError):
            get_undo_history(limit=bad_limit)
