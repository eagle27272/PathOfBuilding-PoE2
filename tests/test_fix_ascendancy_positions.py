import json
import pathlib

import fix_ascendancy_positions


def _write_tree(path: pathlib.Path) -> None:
    path.write_text(
        json.dumps(
            {
                "nodes": {
                    "100": {
                        "ascendancyName": "Juggernaut",
                        "isAscendancyStart": True,
                        "name": "Juggernaut",
                    }
                },
                "groups": {
                    "1": {"x": -10000, "y": 5000, "orbits": [0], "nodes": ["100"]}
                },
                "extraImages": {"background": "ascendancy.png"},
                "sprites": {
                    "notable": {
                        "1": {"filename": "notable.png"},
                        "0.3835": {"filename": "notable-small.png"},
                    },
                    "small": {"0.3835": {"filename": "small.png"}},
                },
                "imageZoomLevels": [1, 0.3835],
            }
        )
    )


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def test_fix_one(tmp_path: pathlib.Path) -> None:
    data_path = tmp_path / "data.json"
    _write_tree(data_path)

    fix_ascendancy_positions.fix_ascendancy_positions(data_path)

    data = _read_json(data_path)
    sprites = _read_json(tmp_path / "sprites.json")
    assert data["groups"]["1"]["x"] == -10400
    assert data["groups"]["1"]["y"] == 5200
    assert "extraImages" not in data
    assert "sprites" not in data
    assert "imageZoomLevels" not in data
    assert data["nodes"]["52435"]["name"] == "Indomitable Resolve"
    assert sprites == {
        "extraImages": {"background": "ascendancy.png"},
        "sprites": {
            "notable": {"filename": "notable.png"},
            "small": {"filename": "small.png"},
        },
    }


def test_fix_all(tmp_path: pathlib.Path) -> None:
    data_path = tmp_path / "nested" / "data.json"
    data_path.parent.mkdir()
    _write_tree(data_path)

    fix_ascendancy_positions.main(tmp_path)

    data = _read_json(data_path)
    assert data["groups"]["1"]["x"] == -10400
    assert data["groups"]["1"]["y"] == 5200
    assert (data_path.parent / "sprites.json").is_file()
