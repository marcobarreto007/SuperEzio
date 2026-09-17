"""Tests for SEC EDGAR getcurrent Atom feed parser."""

from __future__ import annotations

from datetime import UTC, datetime

from core.heart.edgar_atom import parse_edgar_atom

SAMPLE_ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>EDGAR Latest Submissions</title>
  <updated>2026-09-17T02:00:00Z</updated>
  <id>urn:tag:sec.gov,2008:feed-getcurrent</id>
  <entry>
    <title>8-K - Apple Inc. (0000320193) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/0000320193-26-000010-index.htm"/>
    <summary type="html">&lt;b&gt;Filed:&lt;/b&gt; 2026-09-17</summary>
    <updated>2026-09-17T01:30:15Z</updated>
    <category scheme="http://www.sec.gov/" label="form type" term="8-K"/>
    <id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000010</id>
  </entry>
  <entry>
    <title>10-Q - Microsoft Corp (0000789019) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/789019/000078901926000020/0000789019-26-000020-index.htm"/>
    <updated>2026-09-17T01:35:00Z</updated>
    <category scheme="http://www.sec.gov/" label="form type" term="10-Q"/>
    <id>urn:tag:sec.gov,2008:accession-number=0000789019-26-000020</id>
  </entry>
  <entry>
    <title>8-K - Tesla, Inc. (0001318605) (Filer)</title>
    <updated>2026-09-17T01:45:30Z</updated>
    <id>urn:tag:sec.gov,2008:accession-number=0001318605-26-000030</id>
  </entry>
</feed>
"""


def test_parse_edgar_atom_filter_8k():
    events = parse_edgar_atom(SAMPLE_ATOM_FEED, form="8-K")
    assert len(events) == 2

    e0 = events[0]
    assert e0.source == "sec_getcurrent"
    assert e0.event_type == "8-K"
    assert e0.timestamp_precision == "second"
    assert e0.symbol == "0000320193"
    assert "0000320193" in e0.identity
    assert "0000320193-26-000010" in e0.identity
    assert e0.occurred_at == datetime(2026, 9, 17, 1, 30, 15, tzinfo=UTC)

    e1 = events[1]
    assert e1.symbol == "0001318605"
    assert e1.event_type == "8-K"
    assert e1.occurred_at == datetime(2026, 9, 17, 1, 45, 30, tzinfo=UTC)


def test_parse_edgar_atom_all_forms():
    events = parse_edgar_atom(SAMPLE_ATOM_FEED, form=None)
    assert len(events) == 3
    event_types = [e.event_type for e in events]
    assert event_types == ["8-K", "10-Q", "8-K"]


def test_parse_edgar_atom_empty_or_malformed():
    assert parse_edgar_atom(b"") == []
    assert parse_edgar_atom(b"   ") == []
    assert parse_edgar_atom(b"<not-xml") == []


def test_parse_edgar_atom_missing_updated():
    bad_xml = b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>8-K - Sample Corp (0000123456)</title>
        <id>accession-123</id>
      </entry>
    </feed>"""
    assert parse_edgar_atom(bad_xml) == []
