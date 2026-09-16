from core.heart.identities import item_identity


def test_guid_wins():
    assert item_identity(b"<rss/>", guid="spine-guid-1") == "spine-guid-1"


def test_hash_when_no_guid():
    ident = item_identity(b"<rss/>", guid=None)
    assert ident.startswith("sha256:")
