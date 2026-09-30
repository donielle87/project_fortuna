"""Deterministic child-stream derivation for F-E001 (frozen config).

RNG: numpy.random.Generator wrapping PCG64DXSM.
Root seed: 20260930 (config/experiments/F-E001.yaml).

Child derivation ``sha256-scope-v1``:
    H = first 16 bytes of SHA-256("<experiment_id>|<scope>") as a
    big-endian integer;
    child = SeedSequence([root_seed, H]).

The scope string fully determines the stream, so execution order and batch
order cannot change the stream assigned to a unit of work. Python's global
``random`` module and ``numpy.random.seed`` are never used.
"""

import hashlib

import numpy as np


def scope_entropy(experiment_id: str, scope: str) -> int:
    """128-bit big-endian integer from SHA-256 of the scoped label."""
    digest = hashlib.sha256(f"{experiment_id}|{scope}".encode()).digest()
    return int.from_bytes(digest[:16], "big")


def child_seed_sequence(
    root_seed: int, experiment_id: str, scope: str
) -> np.random.SeedSequence:
    """SeedSequence([root_seed, H(scope)]) — deterministic child stream."""
    return np.random.SeedSequence([root_seed, scope_entropy(experiment_id, scope)])


def make_rng(root_seed: int, experiment_id: str, scope: str) -> np.random.Generator:
    """A PCG64DXSM Generator on the deterministic child stream."""
    return np.random.Generator(
        np.random.PCG64DXSM(child_seed_sequence(root_seed, experiment_id, scope))
    )
