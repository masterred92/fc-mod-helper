import importlib


def test_gui_module_imports():
    gui = importlib.import_module("fcmh.gui")
    assert callable(gui.run)
