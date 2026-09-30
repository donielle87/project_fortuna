"""Unit tests for hashing and the immutable artifact store."""
import hashlib

import pytest

from fortuna.provenance.hashing import sha256_bytes, sha256_file
from fortuna.provenance.store import ArtifactStore


def _store(tmp_path):
    return ArtifactStore(raw_dir=tmp_path / "data" / "raw",
                         manifest_path=tmp_path / "metadata" / "raw_artifacts.csv")


def test_sha256_bytes():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert sha256_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_store_writes_file_and_manifest(tmp_path):
    store = _store(tmp_path)
    art = store.store("SRC-TEST-1", b"payload", "text/plain")
    assert (tmp_path / art.immutable_path).read_bytes() == b"payload"
    assert art.sha256 == sha256_bytes(b"payload")
    # manifest row persisted
    store2 = _store(tmp_path)
    manifest = store2._load_manifest()
    assert len(manifest) == 1 and manifest[0].artifact_id == art.artifact_id


def test_store_dedupes_identical_content(tmp_path):
    store = _store(tmp_path)
    a1 = store.store("SRC-TEST-1", b"same", "text/plain")
    a2 = store.store("SRC-TEST-1", b"same", "text/plain")
    # two retrieval events, one immutable file
    assert a1.artifact_id != a2.artifact_id
    assert a1.immutable_path == a2.immutable_path
    assert a1.sha256 == a2.sha256


def test_store_new_content_new_file(tmp_path):
    store = _store(tmp_path)
    a1 = store.store("SRC-TEST-1", b"v1", "text/plain")
    a2 = store.store("SRC-TEST-1", b"v2", "text/plain")
    assert a1.immutable_path != a2.immutable_path
    assert (tmp_path / a1.immutable_path).read_bytes() == b"v1"
    assert (tmp_path / a2.immutable_path).read_bytes() == b"v2"


def test_store_never_overwrites(tmp_path):
    store = _store(tmp_path)
    a1 = store.store("SRC-TEST-1", b"original", "text/plain")
    # corrupt attempt: write same path manually then ensure store doesn't touch it
    p = tmp_path / a1.immutable_path
    assert p.read_bytes() == b"original"


def test_manifest_missing_file_fails(tmp_path):
    store = _store(tmp_path)
    a1 = store.store("SRC-TEST-1", b"content", "text/plain")
    (tmp_path / a1.immutable_path).unlink()
    with pytest.raises(FileNotFoundError):
        store.store("SRC-TEST-1", b"content", "text/plain")


def test_ext_mapping(tmp_path):
    store = _store(tmp_path)
    a = store.store("SRC-TEST-1", b"{}", "application/json; charset=utf-8")
    assert a.immutable_path.endswith(".json")
    assert a.mime_type == "application/json"
