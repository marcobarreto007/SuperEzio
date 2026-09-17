from pathlib import Path

from core.heart.identities import extract_rss_item_guids, item_identity

SPINE_RSS = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "rss.xml"


def test_guid_wins():
    assert item_identity(b"<rss/>", guid="spine-guid-1") == "spine-guid-1"


def test_hash_when_no_guid():
    ident = item_identity(b"<rss/>", guid=None)
    assert ident.startswith("sha256:")


def test_extract_rss_item_guids_from_spine_fixture():
    guids = extract_rss_item_guids(SPINE_RSS.read_bytes())
    assert guids == ["spine-guid-1"]


def test_extract_rss_item_guids_skips_items_without_guid():
    xml = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>x</title>
<item><title>no guid</title></item>
<item><title>has guid</title><guid>g-2</guid></item>
</channel></rss>"""
    assert extract_rss_item_guids(xml) == ["g-2"]
