import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from deepwick_spec.ansi import runs, style_of
from deepwick_spec.check_port import check_port
from deepwick_spec.palette import load_palette
from deepwick_spec.tui import capture, tmux_available

REPO = Path(__file__).resolve().parents[1]
PALETTE = load_palette()
C = PALETTE.colors
CONFIG = REPO / "deepwick.toml"
NAMES = {"Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"}
NAMES |= {"Bright" + n for n in NAMES}
SPECIAL = {"ByPercentage", "ByState", "ByUnit"}



def isolated_env(tmp_path, **extra):
    dirs = {"HOME": tmp_path / "home"}
    for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
        dirs[f"XDG_{kind}_HOME"] = tmp_path / kind.lower()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    env = {key: str(path) for key, path in dirs.items()}
    env.update({key: str(value) for key, value in extra.items()})
    return env


def config():
    assert CONFIG.is_file(), "deepwick.toml missing"
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def color(value):
    dark, light = value.split("|")
    assert dark == light, value
    return dark


def test_columns_and_privacy():
    c = config()
    assert [col["kind"] for col in c["columns"]] == ["Pid", "Separator", "State", "Nice", "UsageCpu", "UsageMem",
                                                     "CpuTime", "Separator", "Command"]
    assert "docker" not in c
    assert c["display"]["show_self"] is False and c["display"]["show_kthreads"] is False
    assert c["display"]["theme"] == "Dark"


def test_only_ansi_names():
    c = config()
    values = [col["style"] for col in c["columns"]]
    values += list(c["style"][k] for k in ("header", "unit", "tree"))
    for group in ("by_percentage", "by_state", "by_unit"):
        values += list(c["style"][group].values())
    for value in values:
        assert value in SPECIAL or color(value) in NAMES, value


def test_roles():
    c = config()
    style = c["style"]
    assert color(style["header"]) == "Blue"
    assert color(c["columns"][0]["style"]) == "Yellow"
    assert color(c["columns"][-1]["style"]) == "White"
    assert {k: color(v) for k, v in style["by_percentage"].items()} == {
        "color_000": "BrightBlack", "color_025": "Green", "color_050": "Yellow", "color_075": "Red", "color_100": "BrightRed"}
    assert color(style["by_state"]["color_r"]) == "Green" and color(style["by_state"]["color_d"]) == "Red"


@pytest.fixture
def workers():
    procs = [subprocess.Popen(["bash", "-c", f"exec -a deepwick-worker-{i} sleep 600"]) for i in (1, 2)]
    yield [p.pid for p in procs]
    for p in procs:
        p.kill()
        p.wait()


@pytest.mark.skipif(not (tmux_available() and shutil.which("procs")), reason="requires tmux and procs")
def test_procs_renders_from_xdg_config(tmp_path, workers):
    env = isolated_env(tmp_path, TERM="tmux-256color")
    target = Path(env["XDG_CONFIG_HOME"]) / "procs" / "config.toml"
    target.parent.mkdir(parents=True)
    shutil.copy(CONFIG, target)
    pids = " ".join(map(str, workers))
    out = capture(f"procs --pager disable --or {pids}; sleep 30", env, size=(120, 10), wait_for="deepwick-worker-2")
    header = next(style for chunk, style in runs(out) if chunk.startswith("PID"))
    assert header["fg"] == "ansi:4"
    assert style_of(out, str(workers[0]))["fg"] == "ansi:3"


def test_port_conventions():
    assert check_port(REPO, PALETTE.allowed_hex()) == []
