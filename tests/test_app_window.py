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


def test_scout_preview_window(root, fake_env, monkeypatch):
    import os
    import time
    from conftest import FIXTURES

    ledger = fake_env.load()
    ledger.app["setup_done"] = True
    ledger.save()
    app = app_mod.App(root, fake_env.ledger_path, probe=EmptyProbe({}), detector=no_detect, no_wait=True)
    app.start()
    root.update()
    app.on_scout()  # no report yet -> instructions, no crash
    folder = logic.scouting_dir(app.ledger)
    source = FIXTURES / "scouting" / "scout_2026-09-01.csv"
    (folder / source.name).write_bytes(source.read_bytes())
    app.poll_scouting()  # main screen: remembers it quietly the first time
    app.on_scout()
    root.update()
    assert app.screen == "scout"
    assert len(app._scout_players()) == 7  # signed one hidden
    app._scout_signed(True)
    assert len(app._scout_players()) == 8
    app._scout_sort("age")
    assert app._scout_players()[0].age == 14
    app.export_scout()
    assert app.last_export.exists()
    # a newer report appears while the screen is open -> it refreshes by itself
    newer = folder / "scout_2026-10-01.csv"
    newer.write_text(source.read_text().replace("Example Striker", "Brand New Kid"))
    later = time.time() + 5
    os.utime(newer, (later, later))
    app.poll_scouting()
    root.update()
    assert app.scout_result.csv == newer
    assert any(p.name == "Brand New Kid" for p in app.scout_result.players)
    app.show_main()
    root.update()
