"""Pure parsing and arithmetic. No LLM can change these calculations."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter


class Problem(ValueError):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.status = code, status
        super().__init__(message)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def parse_csv(text: str, required: set[str], kind: str) -> list[dict]:
    if len(text.encode()) > 1024 * 1024:
        raise Problem("file_too_large", f"{kind}: maximum file size is 1 MiB", 413)
    if "\x00" in text:
        raise Problem("bad_csv", f"{kind}: NUL bytes are not allowed")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not required.issubset(headers):
            raise Problem("bad_headers", f"{kind}: unique headers required, including {', '.join(sorted(required))}")
        rows = []
        for i, row in enumerate(reader, 2):
            if i > 10001:
                raise Problem("too_many_rows", f"{kind}: maximum 10,000 rows")
            if None in row or any(v is None for v in row.values()):
                raise Problem("bad_csv", f"{kind}, row {i}: inconsistent number of columns")
            row = {k: v.strip() for k, v in row.items()}
            if any(len(v) > 250 for v in row.values()):
                raise Problem("field_too_long", f"{kind}, row {i}: cell limit is 250 characters")
            if not row.get("sample_id"):
                raise Problem("bad_sample_id", f"{kind}, row {i}: sample_id is required")
            label_field = "label" if kind == "manifest" else "predicted_label"
            if row[label_field] not in {"0", "1"}:
                raise Problem("bad_label", f"{kind}, row {i}: {label_field} must be 0 or 1")
            row[label_field] = int(row[label_field])
            if kind == "manifest":
                if row["split"] not in {"train", "validation", "test"} or not row["source"]:
                    raise Problem("bad_manifest", f"manifest, row {i}: split must be train/validation/test; source is required")
            elif row.get("score"):
                try:
                    score = float(row["score"])
                except ValueError:
                    score = float("nan")
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise Problem("bad_score", f"{kind}, row {i}: score must be finite and between 0 and 1")
                row["score"] = score
            rows.append(row)
        if not rows:
            raise Problem("empty_csv", f"{kind}: no data rows")
        return rows
    except csv.Error as e:
        raise Problem("bad_csv", f"{kind}: invalid CSV ({e})") from e


def build_bundle(manifest_csv: str, predictions: list[str], metadata: dict | None = None) -> dict:
    if not 1 <= len(predictions) <= 2:
        raise Problem("run_count", "Provide one or two prediction files")
    manifest = parse_csv(manifest_csv, {"sample_id", "split", "source", "label"}, "manifest")
    runs = []
    metadata = metadata or {}
    if not isinstance(metadata, dict):
        raise Problem("bad_metadata", "Metadata must be a JSON object")
    if len(json.dumps(metadata).encode()) > 1024 * 1024:
        raise Problem("file_too_large", "Metadata limit is 1 MiB", 413)
    meta_runs = metadata.get("runs", [])
    if not isinstance(meta_runs, list) or any(not isinstance(x, dict) for x in meta_runs):
        raise Problem("bad_metadata", "metadata.runs must be a list of objects")
    for i, text in enumerate(predictions):
        rows = parse_csv(text, {"sample_id", "predicted_label"}, f"predictions {i+1}")
        meta = meta_runs[i] if i < len(meta_runs) else {}
        runs.append({"id": f"run-{i+1}", "name": str(meta.get("name", f"Run {i+1}"))[:80],
                     "metadata": {k: str(meta[k])[:2000] for k in ["description", "model_version", "threshold", "threshold_selection_split", "preprocessing"] if k in meta},
                     "predictions": rows, "hash": digest(rows)})
    bundle = {"manifest": manifest, "runs": runs, "manifest_hash": digest(manifest), "synthetic": False}
    bundle["validation"] = inspect(bundle)
    return bundle


def inspect(bundle: dict) -> dict:
    rows = bundle["manifest"]
    findings = []
    def add(code, message, severity="warning", **details):
        findings.append({"code": code, "severity": severity, "message": message, **details})
    keys = Counter((r["split"], r["sample_id"]) for r in rows)
    if any(n > 1 for n in keys.values()):
        add("duplicate_manifest", "Duplicate sample IDs within a split; metrics are blocked.", "error")
    labels = {}
    for r in rows:
        labels.setdefault(r["sample_id"], set()).add(r["label"])
    if any(len(v) > 1 for v in labels.values()):
        add("conflicting_labels", "A sample has conflicting labels.", "error")
    tests = {r["sample_id"] for r in rows if r["split"] == "test"}
    if not tests:
        add("no_test_samples", "There are no test examples.", "error")
    for field, code in [("sample_id", "sample_overlap"), ("group_id", "group_overlap"), ("content_hash", "hash_overlap")]:
        by_split = {s: {r.get(field) for r in rows if r["split"] == s and r.get(field)} for s in ["train", "validation", "test"]}
        pairs = []
        for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]:
            common = sorted(by_split[a] & by_split[b])
            if common:
                pairs.append({"splits": [a, b], "count": len(common), "examples": common[:5]})
        if pairs:
            add(code, f"Explicit {field} overlap across supplied splits.", pairs=pairs)
    coverage = []
    for run in bundle["runs"]:
        counts = Counter(r["sample_id"] for r in run["predictions"])
        ids = set(counts)
        if any(n > 1 for n in counts.values()):
            add("duplicate_predictions", f"{run['id']}: duplicate prediction IDs.", "error", run_id=run["id"])
        if ids - tests:
            add("unknown_prediction_ids", f"{run['id']}: predictions contain IDs outside the test manifest.", "error", count=len(ids-tests), run_id=run["id"])
        if tests - ids:
            add("missing_predictions", f"{run['id']}: incomplete test coverage; comparisons are blocked.", run_id=run["id"], count=len(tests-ids))
        meta = run.get("metadata", {})
        if not meta.get("preprocessing") or not meta.get("threshold_selection_split"):
            add("missing_provenance", f"{run['id']}: preprocessing/threshold selection is not assessable from supplied evidence.", run_id=run["id"])
        if meta.get("threshold_selection_split") == "test":
            add("test_threshold_selection", f"{run['id']}: reported threshold was selected using test data.", run_id=run["id"])
        coverage.append({"run_id": run["id"], "matched": len(ids & tests), "total": len(tests), "fraction": len(ids & tests)/len(tests) if tests else None})
    return {"status": "quarantined" if any(x["severity"] == "error" for x in findings) else "ready",
            "findings": findings, "coverage": coverage, "test_samples": len(tests),
            "sources": sorted({r["source"] for r in rows if r["split"] == "test"})[:50],
            "source_count": len({r["source"] for r in rows if r["split"] == "test"}),
            "runs": [{k: r[k] for k in ["id", "name", "hash", "metadata"]} for r in bundle["runs"]],
            "manifest_hash": bundle["manifest_hash"], "synthetic": bundle.get("synthetic", False),
            "limits": "ID/group/exact-hash checks cannot certify preprocessing, near duplicates, or the complete training pipeline."}


def joined(bundle: dict, run_id: str, source: str | None = None) -> tuple[list[tuple], int]:
    if inspect(bundle)["status"] == "quarantined":
        raise Problem("quarantined", "Correct the validation errors before calculating metrics")
    run = next((r for r in bundle["runs"] if r["id"] == run_id), None)
    if not run:
        raise Problem("unknown_run", "Select an existing run ID")
    tests = [r for r in bundle["manifest"] if r["split"] == "test" and (source is None or r["source"] == source)]
    if not tests:
        raise Problem("empty_slice", "No test examples match this source")
    predictions = {r["sample_id"]: r["predicted_label"] for r in run["predictions"]}
    return [(r, predictions[r["sample_id"]]) for r in tests if r["sample_id"] in predictions], len(tests)


def metrics(bundle: dict, run_id: str, source: str | None = None) -> dict:
    pairs, total = joined(bundle, run_id, source)
    counts = {"tn": 0, "fp": 0, "fn": 0, "tp": 0}
    for row, pred in pairs:
        counts[{(0,0): "tn", (0,1): "fp", (1,0): "fn", (1,1): "tp"}[(row["label"], pred)]] += 1
    tn, fp, fn, tp = (counts[k] for k in ["tn", "fp", "fn", "tp"])
    def ratio(a, b): return a/b if b else None
    return {"run_id": run_id, "source": source, "counts": counts, "n": len(pairs), "total": total,
            "coverage": ratio(len(pairs), total), "population": "full test set" if len(pairs)==total else "available predictions only",
            "accuracy": ratio(tp+tn, len(pairs)), "precision": ratio(tp, tp+fp), "recall": ratio(tp, tp+fn),
            "f1": ratio(2*tp, 2*tp+fp+fn), "undefined_reason": "Null metrics have a zero denominator; null does not mean zero."}


def compare(bundle: dict) -> dict:
    if len(bundle["runs"]) != 2:
        raise Problem("two_runs_required", "Import a second run to compare")
    a, b = [metrics(bundle, r["id"]) for r in bundle["runs"]]
    if any(m["coverage"] != 1 for m in [a,b]):
        raise Problem("incomparable", "Both runs must cover the entire same test population; no silent intersection")
    slices = []
    for source in inspect(bundle)["sources"][:20]:
        x,y = [metrics(bundle,r["id"],source) for r in bundle["runs"]]
        slices.append({"source": source, "n": x["n"], "baseline": x, "candidate": y})
    return {"baseline": a, "candidate": b, "deltas": {k: b[k]-a[k] if a[k] is not None and b[k] is not None else None for k in ["accuracy","precision","recall","f1"]},
            "slices": slices, "slice_limit":20, "source_count":inspect(bundle)["source_count"],
            "slices_truncated":inspect(bundle)["source_count"]>20,
            "interpretation": "Deltas are candidate minus baseline, in fraction units (multiply by 100 for percentage points). At most 20 source slices are shown; use source-filtered metrics for others. This is descriptive, not a causal or significance test."}


def errors(bundle: dict, run_id: str, kind: str = "fn", source: str | None = None, offset: int = 0) -> dict:
    if kind not in {"fn", "fp"} or not 0 <= offset <= 10000:
        raise Problem("bad_filter", "kind must be fn/fp and offset between 0 and 10000")
    pairs, _ = joined(bundle,run_id,source)
    found = [r["sample_id"] for r,p in pairs if (r["label"],p)==({"fn":(1,0),"fp":(0,1)}[kind])]
    return {"run_id":run_id,"kind":kind,"source":source,"count":len(found),"sample_ids":found[offset:offset+20],"offset":offset,"has_more":len(found)>offset+20}
