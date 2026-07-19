from core.storage.atomic import atomic_write_bytes, atomic_write_text


def test_atomic_text_replaces_existing_content_without_temp_residue(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, '{"version":2}')

    assert target.read_text(encoding="utf-8") == '{"version":2}'
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_bytes_round_trip(tmp_path):
    target = tmp_path / "vectors.bin"
    atomic_write_bytes(target, b"\x00\x01\x02")
    assert target.read_bytes() == b"\x00\x01\x02"
