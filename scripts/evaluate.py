"""Repeatable synthetic retrieval check, never a scientific QA benchmark."""

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import main

with tempfile.TemporaryDirectory() as temp:
    main.DATA = Path(temp)
    main.initialize()
    corpus = [
        (
            "plants",
            1,
            "Photosynthesis converts light into chemical energy in plants. Chlorophyll captures sunlight.",
        ),
        (
            "citations",
            2,
            "Citation coverage counts claims with references. Citation correctness requires evidence that supports each claim.",
        ),
        (
            "retrieval",
            3,
            "BM25 ranks documents using term frequency and collection statistics. Lexical retrieval can miss synonyms.",
        ),
    ]
    with main.db() as c:
        for name, page, text in corpus:
            c.execute(
                "INSERT INTO papers(id,name,kind,size,digest,status,pages) VALUES(?,?,'pdf',0,?,'ready',3)",
                (name, name, name),
            )
            c.execute(
                "INSERT INTO chunks(paper_id,page,text) VALUES(?,?,?)",
                (name, page, text),
            )
        # Distractors are mechanical load fixtures, not uploaded PDFs.
        for i in range(10000):
            pid = f"distractor-{i}"
            c.execute(
                "INSERT INTO papers(id,name,kind,size,digest,status,pages) VALUES(?,?,'pdf',0,?,'ready',1)",
                (pid, pid, pid),
            )
            c.execute(
                "INSERT INTO chunks(paper_id,page,text) VALUES(?,1,?)",
                (
                    pid,
                    f"Synthetic catalogue entry {i}. Materials analysis and laboratory calibration of measurement instruments.",
                ),
            )
    queries = [
        ("How does photosynthesis use light?", "plants", 1),
        ("What is citation correctness?", "citations", 2),
        ("How does BM25 rank documents?", "retrieval", 3),
    ]
    outcomes = []
    latencies = []
    for question, pid, page in queries:
        start = time.perf_counter()
        sources = main.retrieve(question, [])
        latencies.append((time.perf_counter() - start) * 1000)
        ranks = [
            i + 1
            for i, s in enumerate(sources)
            if s["paper_id"] == pid and s["page"] == page
        ]
        outcomes.append(
            {
                "question": question,
                "expected_paper": pid,
                "expected_page": page,
                "rank": ranks[0] if ranks else None,
            }
        )
    report = {
        "dataset": "3 synthetic labeled questions with 10,000 synthetic distractor documents; not a research QA benchmark",
        "papers": 10003,
        "questions": 3,
        "recall_at_6": sum(o["rank"] is not None for o in outcomes) / 3,
        "mrr": sum(1 / o["rank"] if o["rank"] else 0 for o in outcomes) / 3,
        "retrieval_latency_median_ms": round(statistics.median(latencies), 2),
        "citation_correctness": "not measured; requires claim-support labels",
        "live_generation": "not tested; no provider key configured",
        "results": outcomes,
    }
    print(json.dumps(report, indent=2))
    if report["recall_at_6"] != 1:
        sys.exit(1)
