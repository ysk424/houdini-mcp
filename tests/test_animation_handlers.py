"""Tests for animation handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


def _setup_hou_animation():
    hou = sys.modules["hou"]
    if not hasattr(hou, "Keyframe"):
        class MockKeyframe:
            def __init__(self):
                self._frame = 0
                self._value = 0
                self._expr = None

            def setFrame(self, f):
                self._frame = f

            def setValue(self, v):
                self._value = v

            def frame(self):
                return self._frame

            def value(self):
                return self._value

            def expression(self):
                return self._expr

            def isExpressionSet(self):
                return self._expr is not None

        hou.Keyframe = MockKeyframe
    if not hasattr(hou, "time"):
        hou.time = lambda: 0.0
    if not hasattr(hou, "intFrame"):
        hou.intFrame = lambda: 1
    hou.playbar.setFrameRange = lambda s, e: None
    hou.playbar.setPlaybackRange = lambda s, e: None
    hou.playbar.play = lambda: None
    hou.playbar.stop = lambda: None
    hou.playbar.reverse = lambda: None


class MockParm:
    def __init__(self, name):
        self._name = name
        self._keyframes = []

    def name(self):
        return self._name

    def setKeyframe(self, key):
        self._keyframes.append(key)

    def deleteKeyframeAtFrame(self, frame):
        self._keyframes = [k for k in self._keyframes if k.frame() != frame]

    def keyframes(self):
        return self._keyframes


class MockNodeAnim:
    def __init__(self, parms=None):
        self._parms = {p.name(): p for p in (parms or [])}

    def path(self):
        return "/obj/node1"

    def parm(self, name):
        return self._parms.get(name)


from houdinimcp.handlers.animation import (
    set_keyframes, delete_keyframe, get_keyframes,
    get_frame, set_frame_range, set_playback_range, playbar_control,
)


class TestAnimationHandlers:
    def setup_method(self):
        _setup_hou_animation()
        self._orig_node = sys.modules["hou"].node
        self.parm = MockParm("tx")
        self.node = MockNodeAnim([self.parm])
        sys.modules["hou"].node = lambda p: self.node if p == "/obj/node1" else None

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_set_keyframes(self):
        result = set_keyframes("/obj/node1", "tx", [
            {"frame": 1, "value": 0}, {"frame": 24, "value": 10},
        ])
        assert result["count"] == 2
        assert len(self.parm._keyframes) == 2

    def test_set_keyframes_single(self):
        result = set_keyframes("/obj/node1", "tx", [{"frame": 1.0, "value": 5.0}])
        assert result["count"] == 1
        assert len(self.parm._keyframes) == 1

    def test_delete_keyframe(self):
        set_keyframes("/obj/node1", "tx", [{"frame": 1.0, "value": 5.0}])
        result = delete_keyframe("/obj/node1", "tx", 1.0)
        assert result["deleted"] is True
        assert len(self.parm._keyframes) == 0

    def test_get_keyframes(self):
        set_keyframes("/obj/node1", "tx", [{"frame": 1.0, "value": 5.0}])
        result = get_keyframes("/obj/node1", "tx")
        assert len(result["keyframes"]) == 1

    def test_get_frame(self):
        result = get_frame()
        assert "frame" in result
        assert "time" in result

    def test_set_frame_range(self):
        result = set_frame_range(1, 100)
        assert result["start"] == 1
        assert result["end"] == 100

    def test_set_playback_range(self):
        result = set_playback_range(10, 50)
        assert result["start"] == 10

    def test_playbar_control(self):
        result = playbar_control("play")
        assert result["action"] == "play"

    def test_playbar_control_invalid(self):
        with pytest.raises(ValueError, match="Unknown action"):
            playbar_control("fast_forward")

    def test_set_keyframes_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            set_keyframes("/obj/missing", "tx", [{"frame": 1.0, "value": 0.0}])
