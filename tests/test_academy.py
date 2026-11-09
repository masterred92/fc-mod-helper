import csv

import pytest
from conftest import FIXTURES

from fcmh import academy

ACADEMY = FIXTURES / "academy"


def test_merge_and_growth(tmp_path):
    prospects = academy.merge(academy.collect([ACADEMY]))
    assert set(prospects) == {"460001", "460002", "460003", "460004"}
    a = prospects["460001"]
    assert [s.ovr for s in a.snapshots] == [58, 63, 69]
    assert a.growth() == 11 and a.pot_change() == 2
    assert set(a.by_season()) == {"2026/27", "2027/28"}
    assert a.by_season()["2026/27"].ovr == 63  # last snapshot of the season
    assert prospects["460004"].growth() == 0
    assert prospects["460002"].latest.name == 'Prospect, "Quoted" B'


def test_duplicate_runs_collapse(tmp_path):
    copy = tmp_path / "fcmh_academy_2026-08-01_again.csv"
    copy.write_text((ACADEMY / "fcmh_academy_2026-08-01.csv").read_text())
    prospects = academy.merge(academy.collect([ACADEMY, copy]))
    assert len(prospects["460001"].snapshots) == 3


def test_write_report(tmp_path):
    paths = academy.write_report(academy.merge(academy.collect([ACADEMY])), tmp_path / "out")
    with open(paths["growth"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["playerid"] == "460001"  # biggest grower first
    assert rows[0]["ovr_growth"] == "+11"
    assert rows[0]["ovr_2026/27"] == "63" and rows[0]["ovr_2027/28"] == "69"
    html = paths["html"].read_text(encoding="utf-8")
    assert "<b>Escape Me</b>" not in html and "&lt;b&gt;Escape Me&lt;/b&gt;" in html
    assert "| 460001 |" in paths["markdown"].read_text(encoding="utf-8")
    with open(paths["merged"], newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 8


def test_errors(tmp_path):
    with pytest.raises(academy.AcademyError, match="No academy CSVs"):
        academy.merge(academy.collect([tmp_path]))
    bad = tmp_path / "fcmh_academy_bad.csv"
    bad.write_text("playerid,name\n1,x\n")
    with pytest.raises(academy.AcademyError, match="missing column"):
        academy.merge([bad])
    with pytest.raises(academy.AcademyError, match="Not found"):
        academy.collect([tmp_path / "nope"])
