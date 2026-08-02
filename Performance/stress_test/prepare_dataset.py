#!/usr/bin/env python3
"""Build the stress-test datasets from the Amazon Reviews 2023 corpus
(McAuley Lab, UCSD; https://amazon-reviews-2023.github.io/), replacing the
tiled duplication of the 2.2M-row main-benchmark dataset with genuine data:
the stress sizes up to 80M rows are real review events, no row repeated.

Source: the ``benchmark/0core/rating_only`` files of
``McAuley-Lab/Amazon-Reviews-2023`` - plain CSVs holding only user_id,
parent_asin, rating, timestamp: NO review text, images, product
descriptions, or URLs, which is why ~230M events cost only ~13GB of
download.  Categories: Home_and_Kitchen (~67M), Clothing_Shoes_and_Jewelry
(~66M), Electronics (~44M), Books (~29.5M), Beauty_and_Personal_Care
(~24M) -> ~230M rows in global timestamp order.

Schema mapping to the benchmark CSV contract
(seq_id, category, stars, price, reviews, category_name):
  seq_id        0..N-1 in global timestamp order (the row-pattern axis)
  stars, price  the review rating (1.0-5.0); ``price`` is only used by the
                stress patterns in the always-true guard ``price >= 0``
  reviews       0 (unused by every stress pattern)
  category      the rating rounded to 1..5 and mapped to A..E, so pattern
                variables follow real user-rating sequences over time
  category_name the source category (provenance)

Sizes written: 5M, 10M, 20M, 40M, 80M, 160M, and the FULL corpus (~230M
rows, actual count recorded in datasets/sizes.json) - each a nested prefix
of the same ordered sequence.  To extend beyond 111M in the future (the corpus has
571M reviews total), add more categories to SOURCES (e.g. Books ~29.5M,
Clothing_Shoes_and_Jewelry ~66M) and re-run; see README.md for the
container-limit implications.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "datasets"

BASE_URL = ("https://huggingface.co/datasets/McAuley-Lab/"
            "Amazon-Reviews-2023/resolve/main/benchmark/0core/rating_only")
SOURCES = ["Home_and_Kitchen", "Clothing_Shoes_and_Jewelry",
           "Electronics", "Books", "Beauty_and_Personal_Care"]

SIZES = [5_000_000, 10_000_000, 20_000_000, 40_000_000, 80_000_000,
         160_000_000]

LETTERS = np.array(["A", "B", "C", "D", "E"])


def remote_size(name: str) -> int:
    out = subprocess.run(["curl", "-sIL", f"{BASE_URL}/{name}.csv"],
                         capture_output=True, text=True).stdout
    size = 0
    for line in out.lower().splitlines():
        if line.startswith("content-length:"):
            size = int(line.split(":", 1)[1])
    return size


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        dest = RAW / f"{name}.csv"
        want = remote_size(name)
        have = dest.stat().st_size if dest.exists() else 0
        if want and have == want:
            print(f"  {dest.name} complete ({have/1e9:.1f} GB)")
            continue
        print(f"  downloading {name}.csv ({have/1e9:.1f}/{want/1e9:.1f} GB)")
        subprocess.run(["curl", "-L", "-C", "-", "-o", str(dest),
                        f"{BASE_URL}/{name}.csv"], check=True)
        got = dest.stat().st_size
        assert not want or got == want, f"{name}: {got} != {want} bytes"


def build() -> None:
    frames = []
    for name in SOURCES:
        print(f"  reading {name}.csv (rating, timestamp only)")
        df = pd.read_csv(RAW / f"{name}.csv",
                         usecols=["rating", "timestamp"],
                         dtype={"rating": "float32", "timestamp": "float64"})
        n_raw = len(df)
        df = df.dropna(subset=["rating", "timestamp"])
        if len(df) < n_raw:
            print(f"    dropped {n_raw - len(df):,} rows with missing values")
        df["timestamp"] = df["timestamp"].astype("int64")
        df["source"] = name
        frames.append(df)
        print(f"    {len(df):,} rows")
    allr = pd.concat(frames, ignore_index=True)
    del frames
    print(f"  total {len(allr):,} rows; sorting by timestamp")
    allr = allr.sort_values("timestamp", kind="stable", ignore_index=True)
    print(f"  keeping ALL {len(allr):,} rows "
          f"({pd.to_datetime(allr.timestamp.iloc[0], unit='ms'):%Y-%m}"
          f" .. {pd.to_datetime(allr.timestamp.iloc[-1], unit='ms'):%Y-%m})")

    rating = allr["rating"].to_numpy()
    idx = np.clip(np.round(rating), 1, 5).astype(np.int8) - 1
    prepared = pd.DataFrame({
        "seq_id": np.arange(len(allr), dtype=np.int64),
        "category": pd.Categorical.from_codes(idx, categories=list(LETTERS)),
        "stars": rating,
        "price": rating,
        "reviews": np.zeros(len(allr), dtype=np.int8),
        "category_name": pd.Categorical(allr["source"]),
    })
    del allr
    print("  category distribution (%):")
    print((prepared.category.value_counts(normalize=True)
           .sort_index() * 100).round(1).to_string())

    OUT.mkdir(parents=True, exist_ok=True)
    all_sizes = SIZES + [len(prepared)]
    for size in all_sizes:
        path = OUT / f"benchmark_{size}.csv"
        prepared.iloc[:size].to_csv(path, index=False)
        print(f"  wrote {path.name} ({size:,} rows)")
    import json
    (OUT / "sizes.json").write_text(json.dumps(
        {"sizes": all_sizes, "full_size": len(prepared),
         "sources": SOURCES}, indent=2))
    print(f"  manifest: sizes.json (full={len(prepared):,})")


if __name__ == "__main__":
    download()
    build()
    print("stress datasets ready:", OUT)
