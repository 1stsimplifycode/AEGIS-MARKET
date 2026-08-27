"""Generate outputs/week4/EVIDENCE_BLOCK.txt from the actual Week 4 artifacts.

    python scripts/build_week4_evidence.py

Every number below is read from an artifact or recomputed here. Absences are printed as
absences.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

OUT = REPO_ROOT / "outputs" / "week4" / "EVIDENCE_BLOCK.txt"

lines: list[str] = []
w = lines.append


def head(t):
    w("")
    w("=" * 78)
    w(t)
    w("=" * 78)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


w("=" * 78)
w("WEEK 4 EVIDENCE BLOCK -- AEGIS-MARKET (Multimodal Preparation)")
w("Every figure is read from an artifact on disk or recomputed by this script.")
w("=" * 78)

# ------------------------------------------------------------------ C1
head("C1 -- SINGLE UPSTREAM PREPARATION PASS")
from research.preparation import orchestrator as O  # noqa: E402

man = O.load_manifest()
w("")
w("[ENTRY POINT] one orchestrator, executed to produce everything below")
w("  module      : %s" % man["generated_by"])
w("  script      : %s" % man["entry_point"])
w("  version     : %s   seed: %s" % (man["preparation_version"], man["seed"]))
w("  generated_at: %s" % man["generated_at"])
w("  manifest    : data/prepared/week4/PREPARATION_MANIFEST.json")
w("  %s" % man["single_pass_note"])
w("")
w("[SOURCES PREPARED -- each taken from RAW MEDIA in this one call]")
for e in man["sources"]:
    w("  %s  (%s, %s)" % (e["source_id"], e["modality"], e["designation"]))
    w("     raw            : %s" % e["raw"]["description"])
    w("     raw files read : %d      loaded_from_raw_media=%s"
      % (e["raw"]["n_raw_files"], e["raw"]["loaded_from_raw_media"]))
    w("     raw provenance : %s" % e["raw"]["provenance_manifest"])
    w("     provenance sha : %s" % e["raw"]["provenance_manifest_sha256"])
    w("     seed           : %s   randomness: %s" % (e["seed"], e["randomness"]))
    w("     split          : %s, seed %s" % (e["split_strategy"], e["split_seed"]))
    for split in ("train", "val", "test"):
        r = e["outputs"][split]
        w("     %-5s %-22s n=%-6d dtype=%s  sha256=%s"
          % (split, tuple(r["shape"]), r["n"], r["dtype"], r["file_sha256"][:32]))
    w("     parameters recorded:")
    for k, v in e["parameters"].items():
        w("        %-24s %s" % (k, v))
    w("")

w("[EVERY SEED IS RECORDED -- the audit found seed=None on three datasets]")
for e in man["sources"]:
    w("  %-26s seed=%s  split_seed=%s" % (e["source_id"], e["seed"], e["split_seed"]))

w("")
w("[RAW -> PARAMETERS -> PREPARED -> CONSUMER, verifiable]")
v = O.verify(man)
w("  checksum re-derivation from disk: all_match=%s over %d arrays"
  % (v["all_match"], len(v["checked"])))
w("  parameter fingerprint          : %s" % O.parameter_fingerprint(man))
w("  consumers must call load_prepared(), which refuses an unregistered source and")
w("  refuses any array whose checksum disagrees with this manifest.")

w("")
w("[WHICH PREPARED ARRAYS HAVE A DOWNSTREAM CONSUMER TODAY -- stated plainly]")
w("  image_chart_windows  -> research.image.basis (the Week 4 SVD basis) reads it via")
w("                          load_prepared and the basis is projected in tests.")
w("  all three sources    -> scripts/run_week4_equalisation_report.py reads all three")
w("                          via load_prepared to measure the equalisation.")
w("  audio / video        -> NO learned component consumes the Week 4 arrays yet. The")
w("                          existing audio, video and fusion models were trained on the")
w("                          historical V1 datasets and are deliberately left on them so")
w("                          their published results stay reproducible. Retraining them")
w("                          on the Week 4 arrays is downstream work, not Week 4")
w("                          preparation, and is NOT claimed here.")
w("  What IS established: no learned component performs its own preparation, and every")
w("  consumer of a Week 4 array goes through the checksum-gated load_prepared().")
w("")
w("[HISTORICAL ARTIFACTS PRESERVED]")
for k, ok in man["historical_artifacts_preserved"]["checked"].items():
    w("  %-44s present=%s" % (k, ok))
w("  policy: %s" % man["historical_artifacts_preserved"]["policy"])

# ------------------------------------------------------------------ C2
head("C2 -- SOURCE EQUALISATION")
w("")
w("[TARGET -- declared, continuous]")
for k, val in man["equalisation_target"].items():
    w("  %-22s %s" % (k, val))
w("")
w("[METHOD]")
for k, val in man["equalisation_method"].items():
    w("  %-24s %s" % (k, val))
w("")
w("[PER-SOURCE RESULT -- measured on the actual prepared data]")
w("  %-26s %10s %10s %10s %12s" % ("source", "KS", "totalVar", "chi2/bin", "normEntropy"))
for e in man["sources"]:
    eq = e["equalisation"]
    b, a = eq["distribution_before"], eq["distribution_after"]
    w("  %-26s %10s %10s %10s %12s" % (e["source_id"], "", "", "", ""))
    w("    before (raw, scaled)     %10.6f %10.6f %10.4f %12.6f"
      % (b["ks_deviation"], b["total_variation"], b["chi_square_per_bin"],
         b["normalised_entropy"]))
    w("    after  (equalised)       %10.6f %10.6f %10.4f %12.6f"
      % (a["ks_deviation"], a["total_variation"], a["chi_square_per_bin"],
         a["normalised_entropy"]))
    s = eq["shortfall"]
    w("    source dtype=%s distinct levels=%d"
      % (s["source_dtype"], s["n_distinct_source_values"]))
    w("    DISCRETE SHORTFALL vs the continuous target:")
    w("       residual KS              %.6f" % s["residual_ks_deviation"])
    w("       residual total variation %.6f" % s["residual_total_variation"])
    w("       residual chi2 per bin    %.4f" % s["residual_chi_square_per_bin"])
    w("       entropy gap from flat    %.6f" % s["entropy_gap_from_flat"])
    w("       improvement in KS        %.6f" % s["improvement_ks"])
    for r in s["why_not_zero"]:
        w("       why not zero: %s" % r)
    w("       %s" % s["not_tuned"])
    w("    per-split normalised entropy: %s"
      % {k2: round(v2["normalised_entropy"], 6)
         for k2, v2 in eq["per_split_after"].items()})
    w("")
w("  Mean/std standardisation is NOT reported as equalisation anywhere: it is an affine")
w("  map and cannot change distribution shape.")

# ------------------------------------------------------------------ C3
head("C3 -- CONVOLUTION SIZING AND FROZEN GEOMETRY")
from research.models import geometry as G  # noqa: E402

sizing = json.loads((REPO_ROOT / "outputs" / "week4" / "conv_sizing.json")
                    .read_text(encoding="utf-8"))
contract = G.load_contract()
w("")
w("[COMPUTE CONVENTION -- one convention, stated once]")
for k, val in G.COMPUTE_CONVENTION.items():
    w("  %-28s %s" % (k, val))
w("")
w("[SIZING TABLE -- derived by forward hooks on instantiated models]")
for kind, t in sizing.items():
    w("  %s -- %s  input %s   (derived_by: %s)"
      % (kind, t["model"], tuple(t["input_shape"]), t["derived_by"]))
    w("    %-14s %-8s %-20s %-10s %-8s %-8s %-8s %-20s %10s %14s %14s"
      % ("layer", "type", "input", "kernel", "stride", "pad", "dil", "output",
         "params", "MACs", "FLOPs"))
    for r in t["layers"]:
        w("    %-14s %-8s %-20s %-10s %-8s %-8s %-8s %-20s %10s %14s %14s"
          % (r["layer"], r["type"], tuple(r["input_shape"]),
             r.get("kernel_size", "-"), r.get("stride", "-"), r.get("padding", "-"),
             r.get("dilation", "-"), tuple(r["output_shape"]),
             format(r["parameters"], ","), format(r["macs"], ","),
             format(r["flops"], ",")))
    w("    totals: conv layers %d, parameters %s, conv MACs %s, conv FLOPs %s"
      % (t["conv_layers"], format(t["total_parameters"], ","),
         format(t["conv_macs"], ","), format(t["conv_flops"], ",")))
    w("")

w("[FROZEN GEOMETRY CONTRACT]")
w("  artifact   : research_artifacts/models/week4_geometry_contract.json")
w("  fingerprint: %s" % contract["contract_fingerprint"])
for kind, entry in contract["geometries"].items():
    w("  %-7s %-20s input %s  fingerprint %s"
      % (kind, entry["model"], tuple(entry["input_shape"]), entry["fingerprint"][:32]))
w("  selection rule: %s" % contract["selection_rule"])
w("")
w("[DOWNSTREAM WEEKS ARE TIED TO IT -- checked here, not asserted]")
for week, kinds in contract["downstream_consumers"].items():
    for kind in kinds:
        out = G.assert_geometry(kind, week)
        w("  %-7s consumes %-7s -> assert_geometry ok=%s" % (week, kind, out["ok"]))
res = G.verify_contract(contract)
w("  live models still match the freeze: all_match=%s" % res["all_match"])
w("")
w("[HISTORICAL GEOMETRIES -- preserved, and NOT claimed identical]")
for h in contract["historical_geometries_preserved"]:
    w("  %-34s frames=%-5s size=%-4s channels=%-4s selected_for_week4=%s"
      % (h["variant"], h["frames"], h["size"], h["channels"], h["selected_for_week4"]))
w("  %s" % contract["what_a_change_breaks"])

# ------------------------------------------------------------------ C4
head("C4 -- IMAGE BASIS BY DIRECT SVD")
try:
    from research.image import basis as B  # noqa: E402

    rep = B.report()
    w("")
    w("[METHOD]")
    for k, val in rep["method"].items():
        w("  %-22s %s" % (k, val))
    w("")
    w("[MATRIX DECOMPOSED]")
    for k, val in rep["source"].items():
        w("  %-28s %s" % (k, val))
    w("")
    w("[RETENTION -- threshold declared before the curve]")
    for k, val in rep["retention"].items():
        w("  %-38s %s" % (k, val))
    w("")
    w("[SINGULAR VALUES]")
    sv = rep["singular_values"]
    w("  count %d  largest %.6e  smallest %.6e  condition %.6e"
      % (sv["count"], sv["largest"], sv["smallest"],
         sv["condition_number"] or float("nan")))
    w("  first 10: %s" % [round(x, 4) for x in sv["first_20"][:10]])
    w("")
    w("[ENERGY VERSUS NUMBER OF DIRECTIONS]")
    w("  %12s %22s %18s" % ("directions", "cumulative_energy", "singular_value"))
    for p in rep["energy_curve"]:
        w("  %12d %22.8f %18.6e"
          % (p["directions"], p["cumulative_energy"], p["singular_value"]))
    w("")
    w("[RECONSTRUCTION]")
    for k, val in rep["reconstruction"].items():
        w("  %-32s %s" % (k, val))
    w("")
    w("[NOT COVARIANCE-DERIVED -- proved, forbidden route computed for contrast]")
    for k, val in rep.get("covariance_check", {}).items():
        w("  %-56s %s" % (k, val))
    w("  contrast, np.cov route:")
    for k, val in rep.get("covariance_route_for_contrast", {}).items():
        w("     %-32s %s" % (k, val))
    w("")
    w("[ARTIFACT AND DOWNSTREAM CONSUMPTION]")
    for k, val in rep["artifact"].items():
        w("  %-16s %s" % (k, val))
    w("  consumer: research.image.basis.project() returns coordinates in this basis;")
    w("            tests/week4/test_image_basis.py exercises it on the real images.")
except FileNotFoundError:
    w("")
    w("  NOT BUILT: run scripts/run_week4_image_basis.py")

# ------------------------------------------------------------------ C5
head("C5 -- FINANCE INPUTS (A-E)")
from research.media import av_sources as AV  # noqa: E402
from research.media import capture_conditions as CC  # noqa: E402
from research.media import clip_selection as CS  # noqa: E402
from research.media import retention as RET  # noqa: E402
from research.reference import results_calendar as RC  # noqa: E402

av = AV.load()
w("")
w("[C5.A AUDIO-VISUAL SOURCE LIST]  artifact: outputs/week4/av_sources.json")
w("  INGESTED (%d):" % av["counts"]["ingested"])
for s in av["ingested_sources"]:
    w("    %s -- %s" % (s["source_id"], s["title"]))
    w("       url=%s  doi=%s" % (s["url"], s["doi"]))
    w("       access=%s" % s["access_method"])
    w("       licence=%s  verified=%s" % (s["licence"], s["licence_verified"]))
    w("       provenance=%s" % s["licence_provenance"])
    w("       permitted=%s" % s["permitted_use"])
    w("       restrictions=%s" % s["restrictions"])
    w("       retrieved_at=%s  files=%s  archives_with_checksums=%s"
      % (s["retrieved_at"], s["n_media_files"], s["archives_with_checksums"]))
    w("       is_finance_media=%s -- %s"
      % (s["is_finance_media"], s["is_finance_media_note"]))
w("  REFERENCED ONLY (%d):" % av["counts"]["referenced_only"])
for s in av["referenced_only_sources"]:
    w("    %-26s providers=%s" % (s["source_id"], s["providers"]))
    w("       access=%s" % s["access_method"])
    w("       licence=%s  verified=%s" % (s["licence"], s["licence_verified"]))
    w("       stored=%s" % s["what_is_stored"])
w("  FINANCE AV STATUS:")
st = av["finance_av_status"]
w("    obtained=%s" % st["obtained"])
w("    %s" % st["statement"])
for r in st["routes_considered"]:
    w("      route: %-52s -> %s" % (r["route"], r["result"]))
w("    consequence: %s" % st["consequence"])
w("  finance_media_ingested count: %d" % av["counts"]["finance_media_ingested"])

cc = CC.load()
w("")
w("[C5.B CAPTURE-CONDITION DIFFERENCES]  artifact: outputs/week4/capture_conditions.json")
w("  probe method: %s" % cc["probe_method"])
for s in cc["sources"]:
    w("    %s (%s, finance_media=%s)"
      % (s["source_id"], s["modality"], s["is_finance_media"]))
    for k, val in s["probed"].items():
        w("       probed  %-26s %s" % (k, val))
    for k, val in s["documented"].items():
        w("       stated  %-26s %s" % (k, val))
w("  cross-source differences:")
for k, val in cc["cross_source_differences"].items():
    w("    %-26s %s" % (k, val))
w("  unavailable-field policy: %s" % cc["unavailable_fields_policy"])

rc = RC.summary()
w("")
w("[C5.C RESULTS CALENDAR]  artifact: %s" % rc["artifact"]["path"])
w("  rows=%d issuers=%d sessions=%d  %s .. %s"
  % (rc["rows"], rc["issuers"], rc["sessions"], rc["first_session"], rc["last_session"]))
w("  event types: %s" % rc["event_type_counts"])
w("  with real publication timestamp: %d (coverage %.4f)"
  % (rc["with_publication_timestamp"], rc["publication_timestamp_coverage"]))
w("  disseminated after the %s close: %d"
  % (rc["session_close_ist"], rc["disseminated_after_session_close"]))
w("  provenance:")
for k, val in rc["provenance"].items():
    w("     %-26s %s" % (k, val))
w("  sha256=%s bytes=%d" % (rc["artifact"]["sha256"][:32], rc["artifact"]["bytes"]))
w("  %s" % rc["what_was_not_done"])

cs = CS.load()
w("")
w("[C5.D CLIP-SELECTION RULE]  artifact: outputs/week4/clip_selection.json")
w("  consumes: %s" % cs["consumes"])
r = cs["rule"]
w("  qualifying event types : %s" % r["qualifying_event_types"])
w("  timing window (minutes): %s" % r["timing_window_minutes"])
w("  minimum evidence       : %s" % r["minimum_evidence"])
w("  exclusion conditions   :")
for k, val in r["exclusion_conditions"].items():
    w("     %-28s %s" % (k, val))
w("  a selected clip is     : %s" % r["selected_clip_definition"]["what_it_is"])
w("  rule fingerprint       : %s" % cs["rule_fingerprint"])
w("  APPLIED TO REAL EVENTS : candidates=%d selected=%d rejected=%d issuers=%d"
  % (cs["candidates"], cs["n_selected"], cs["n_rejected"], cs["issuers_selected"]))
w("  rejection reasons      : %s" % cs["rejected_counts"])
if cs["selected_sample"]:
    ex = cs["selected_sample"][0]
    w("  example SELECTED       : %s %s %s window %s .. %s"
      % (ex["symbol"], ex["event_type"], ex["disseminated_at"],
         ex["window_start"], ex["window_end"]))
if cs["rejected_sample"]:
    ex = cs["rejected_sample"][0]
    w("  example REJECTED       : %s %s reason=%s"
      % (ex.get("symbol"), ex.get("event_type"), ex.get("reason")))
w("  clips actually acquired: %d" % cs["media_availability"]["clips_actually_acquired"])
w("  blocked by             : %s" % cs["media_availability"]["blocked_by"])
w("  %s" % cs["media_availability"]["why"])

ret = RET.load()
w("")
w("[C5.E RETENTION / TAKEDOWN]  artifact: outputs/week4/retention_policy.json")
w("  default rule: %s" % ret["policy"]["default_rule"])
w("  enforced by:")
for e2 in ret["policy"]["enforced_by"]:
    w("     %s" % e2)
w("  per source:")
for s in ret["policy"]["per_source"]:
    w("     %s" % s["source_id"])
    w("        terms_established=%s licence=%s" % (s["terms_established"], s["licence"]))
    w("        provenance=%s" % s["licence_provenance"])
    w("        retention=%s" % s["retention"])
    w("        deletion_condition=%s" % s["deletion_condition"])
w("  takedown mechanism:")
for k, val in ret["takedown_mechanism"].items():
    w("     %-20s %s" % (k, val))
w("  scope limit: %s" % ret["policy"]["scope_limit"])

# ------------------------------------------------------------------ C6
head("C6 -- WEEK 3 CLOSURE")
from research.week3 import closure as C  # noqa: E402

rec = C.load()
w("")
w("[PERSISTED ARTIFACT] outputs/week3/CLOSURE.json")
w("  closure_version %s  generated_by %s"
  % (rec["closure_version"], rec["generated_by"]))
w("  generated_at    %s" % rec["generated_at"])
w("")
w("[AUDITOR RESULT AS PERSISTED]")
a = rec["auditor"]
w("  verdict  : %s" % a["verdict"])
w("  blocking : %s" % a["blocking"])
for k, val in a["criteria"].items():
    w("  %-8s %s" % (k, val))
w("  judged_from: %s" % a["judged_from"])
w("")
w("[VERIFICATION SUITES -- counts parsed from actual pytest runs]")
for s in rec["verification"]:
    w("  %-40s passed=%-6s skipped=%-4s failed=%-3s exit=%s"
      % (s["label"], s["passed"], s["skipped"], s["failed"], s["exit_code"]))
    w("      command=%s" % s["command"])
    w("      ran_at=%s  measured_by=%s" % (s["ran_at"], s["measured_by"]))
w("")
w("[C3 REPRODUCTION -- recomputed from the stored predictions]")
rp = rec["c3_reproduction"]
for k in ("evaluation_documents", "identical_predictions", "differing_predictions",
          "recomputed_agrees_with_artifact", "winner", "winner_from",
          "margin_macro_f1", "baseline_beat_the_learned_representation"):
    w("  %-42s %s" % (k, rp[k]))
w("")
w("[CONSISTENCY CHECKS RE-RUN NOW]")
res = C.verify(rec)
for k, val in res["checks"].items():
    w("  %-44s %s" % (k, val))
w("  ok: %s" % res["ok"])
w("")
w("[NO WEEK 4 CHANGE INVALIDATED WEEK 3]")
for art in rec["artifacts"]:
    p = REPO_ROOT / art["path"]
    w("  %-38s recorded=%s  now=%s  match=%s"
      % (art["path"], art["sha256"][:16], sha(p)[:16], sha(p) == art["sha256"]))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print("written: %s (%d lines)" % (OUT, len(lines)))
