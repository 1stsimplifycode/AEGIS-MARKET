"""Build the Week 3 market-text intelligence pipeline.

    python scripts/build_week3_text.py --acquire   # fetch announcement text, then build
    python scripts/build_week3_text.py             # build from what is on disk

Stages run in dependency order and each writes a real artifact:

    data/reference/announcement_corpus.parquet          real NSE announcement text
    data/models/text/market_tokenizer_v1/               BPE trained from scratch
    data/models/text/market_tfidf_v1/                   smoothed TF-IDF baseline
    data/models/text/market_embedding_v1/               skip-gram + negative sampling
    data/models/text/market_sentence_encoder_v1/        sentence attention pooling
    data/models/text/registry.json                      trained_here vs pretrained
    data/reference/week3_finance_inputs.json            the four C6 inputs, graded
    outputs/week3/text_summary.json                     everything measured, in one place

Splits are fixed by session and never re-cut: documents from the first 80% of sessions
train, the next 10% validate, the last 10% are the final evaluation and are read exactly
once at the end. No hyperparameter is chosen against the evaluation split.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.core import paths  # noqa: E402
from research.reference import announcements as AN  # noqa: E402
from research.reference import read_manifest, write_manifest  # noqa: E402
from research.text import embeddings as EMB  # noqa: E402
from research.text import finance_inputs as FI  # noqa: E402
from research.text import frequency_baseline as FB  # noqa: E402
from research.text import market_tokenizer as MT  # noqa: E402
from research.text import registry as REG  # noqa: E402
from research.text import sentence_encoder as SE  # noqa: E402
from research.text import vocabulary as VOC  # noqa: E402

#: Session-level split. Chronological, so a model never trains on a session it is later
#: evaluated on, and never sees a future session while training.
TRAIN_FRACTION = 0.80
VALIDATION_FRACTION = 0.10


def split_by_session(corpus: pd.DataFrame) -> dict:
    sessions = sorted(corpus["session"].unique())
    n = len(sessions)
    n_train = int(n * TRAIN_FRACTION)
    n_val = int(n * VALIDATION_FRACTION)
    train_s = set(sessions[:n_train])
    val_s = set(sessions[n_train:n_train + n_val])
    eval_s = set(sessions[n_train + n_val:])
    return {
        "train": corpus[corpus["session"].isin(train_s)],
        "validation": corpus[corpus["session"].isin(val_s)],
        "evaluation": corpus[corpus["session"].isin(eval_s)],
        "sessions": {"train": len(train_s), "validation": len(val_s),
                     "evaluation": len(eval_s)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--acquire", action="store_true")
    ap.add_argument("--from-session", default="2025-08-01")
    args = ap.parse_args()

    paths.ensure_dirs()
    out = paths.REPO_ROOT / "outputs" / "week3"
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"built_at": datetime.now(UTC).isoformat()}

    if args.acquire:
        print("acquiring NSE announcement text ...")
        cal = pd.read_parquet(paths.REFERENCE / "session_calendar.parquet")
        sess = [d.date() for d in cal["session"]
                if d >= pd.Timestamp(args.from_session)]
        corpus, src = AN.acquire(sess)
        others = [s for s in read_manifest() if s.input_id != "announcement_corpus"]
        write_manifest(others + [src])
        print("  %d announcements" % len(corpus))

    corpus = AN.load()
    stats = AN.corpus_stats(corpus)
    summary["corpus"] = stats
    splits = split_by_session(corpus)
    summary["splits"] = splits["sessions"]
    summary["splits"]["train_documents"] = int(len(splits["train"]))
    summary["splits"]["evaluation_documents"] = int(len(splits["evaluation"]))
    print("corpus: %d announcements, %d words, %d sessions"
          % (stats["records"], stats["total_words"], stats["sessions"]))
    print("splits: %s" % splits["sessions"])

    # -- C1 tokenizer ---------------------------------------------------------------
    print("\nC1: selecting vocabulary size and training the tokenizer ...")
    t0 = time.time()
    selection = MT.select_vocab_size(corpus=splits["train"])
    tokenizer, tok_record = MT.train(selection["selected_vocab_size"],
                                     corpus=splits["train"])
    summary["c1_tokenizer"] = {
        **tok_record.to_dict(),
        "selection": selection,
        "provenance_verified": MT.verify_provenance(),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    print("  vocab %d, %d learned merges, %.1fs"
          % (tok_record.vocab_size_final, tok_record.learned_merges,
             time.time() - t0))

    # -- C2 vocabulary analysis -----------------------------------------------------
    print("C2: vocabulary and market-term analysis ...")
    t0 = time.time()
    vocab_report = VOC.analyse(tokenizer, corpus=corpus)
    VOC.save(vocab_report)
    summary["c2_vocabulary"] = vocab_report
    print("  mean seq len %.2f | market terms single-token %d/%d | control %d/%d"
          % (vocab_report["mean_sequence_length"], vocab_report["terms_single_token"],
             vocab_report["terms_present"],
             vocab_report.get("control", {}).get("terms_single_token", 0),
             vocab_report["terms_present"]))

    # -- C3 frequency baseline ------------------------------------------------------
    print("C3: smoothed TF-IDF baseline ...")
    t0 = time.time()
    vec, matrix, fb_record = FB.build(corpus=splits["train"], tokenizer=tokenizer)
    weights = FB.term_weights(vec, list(VOC.MARKET_TERMS))
    summary["c3_frequency_baseline"] = FB.summary(fb_record, weights)
    summary["c3_frequency_baseline"]["elapsed_seconds"] = round(time.time() - t0, 1)
    print("  vocab %d, matrix %s, %.1fs"
          % (fb_record.vocabulary_size, fb_record.matrix_shape, time.time() - t0))

    # -- C4 embeddings --------------------------------------------------------------
    print("C4: skip-gram with negative sampling ...")
    t0 = time.time()
    centre, context, vocab, emb_record = EMB.train(corpus=splits["train"],
                                                   tokenizer=tokenizer)
    movement = EMB.parameter_movement()
    neighbours = EMB.evaluate(vocab["itos"], centre,
                              ("dividend", "bonus", "merger", "allotment", "promoter"))
    summary["c4_embeddings"] = {
        **emb_record.to_dict(),
        "parameter_movement": movement,
        "nearest_neighbours": neighbours,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    print("  vocab %d, dim %d, K=%d, final loss %.4f, params changed %s, %.1fs"
          % (emb_record.vocabulary_size, emb_record.dim, emb_record.negative_k,
             emb_record.epoch_losses[-1], movement["parameters_changed"],
             time.time() - t0))

    # -- C5 sentence encoder + attention --------------------------------------------
    print("C5: sentence encoder and attention pooling ...")
    t0 = time.time()
    encoder = SE.SentenceEncoder(vocab["itos"], centre, tokenizer=tokenizer)
    eval_texts = splits["evaluation"]["body"].tolist()[:5000]
    check = SE.verify(encoder, eval_texts)
    SE.save(encoder, {"verification": check.to_dict()})
    summary["c5_sentence_encoder"] = {
        **SE.record(),
        "verification": check.to_dict(),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    print("  %d docs, %d multi-sentence, weight-sum error %.2e, range violations %d"
          % (check.documents, check.multi_sentence_documents,
             check.max_weight_sum_error, check.range_violations))

    # -- C6 finance inputs ----------------------------------------------------------
    print("C6: finance text inputs ...")
    FI.save()
    summary["c6_finance_inputs"] = FI.report()
    print("  %d/4 fully obtained | %s"
          % (summary["c6_finance_inputs"]["fully_obtained"],
             summary["c6_finance_inputs"]["states"]))

    # -- registry --------------------------------------------------------------------
    REG.save()
    summary["registry"] = REG.load()
    print("\nregistry: %d entries, all trained_here"
          % len(summary["registry"]["entries"]))

    (out / "text_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("summary: %s" % (out / "text_summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
