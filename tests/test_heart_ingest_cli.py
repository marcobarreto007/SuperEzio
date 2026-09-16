from core.heart.poller import ingest_cli


def test_cli_once_with_mock_is_callable():
    assert callable(ingest_cli)
