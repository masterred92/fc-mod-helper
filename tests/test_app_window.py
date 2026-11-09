"""Opens the real window off-screen and presses the buttons through their handlers.
Skipped when there is no display (e.g. a headless Linux runner without Xvfb)."""

import pytest
from conftest import no_detect

tk = pytest.importorskip("tkinter")

from fcmh import app as app_mod  # noqa: E402
from fcmh import app_logic as logic  # noqa: E402
from fcmh import detect  # noqa: E402


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    window.geometry("940x780")
    yield window
    window.destroy()


class EmptyProbe(detect.Probe):
    def __init__(self, env):
        self._env = env

    def env(self, name):
        return self._env.get(name)

    def drives(self):
        return []

    def registry_values(self):
        return []


def test_first_run_and_buttons(root, fake_env, monkeypatch):
    env = {"USERPROFILE": str(fake_env.profile), "LOCALAPPDATA": str(fake_env.lad)}
    new_ledger = fake_env.root / "fresh" / "ledger.json"
    app = app_mod.App(root, new_ledger, probe=EmptyProbe(env), detector=no_detect, no_wait=True)
    app.start()
    root.update()
    app.show_setup()  # nothing found -> yellow items, finish disabled
    assert app.setup_state["install"] is None
    app.setup_state["install"] = fake_env.install
    app.render_setup()
    app.finish_setup()
    root.update()
    assert logic.load_ledger(new_ledger) is not None
    app.on_online()
    app.on_backup()
    app.auto_answers = [None]
    app.on_restore()
    opened = []
    monkeypatch.setattr(app_mod.webbrowser, "open", opened.append)
    app.on_academy()
    app.auto_answers = [None]
    app.on_play()  # no Mod Manager -> plain sentence + fix, nothing launched
    assert app.current_status.fix == "pick_mod_manager"
    app.poll_mods_folder()
    root.update()


def test_self_test():
    assert app_mod.self_test() == 0
