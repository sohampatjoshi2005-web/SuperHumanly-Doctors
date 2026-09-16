from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.transcription_service import transcribe_audio


@dataclass
class BenchmarkSample:
    audio_path: str
    reference: str
    sample_id: str


def normalize_for_metrics(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _edit_distance(seq1: list[str], seq2: list[str]) -> int:
    rows = len(seq1) + 1
    cols = len(seq2) + 1
    dp = [[0] * cols for _ in range(rows)]

    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = normalize_for_metrics(reference).split()
    hyp_words = normalize_for_metrics(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return _edit_distance(ref_words, hyp_words) / len(ref_words)


def char_error_rate(reference: str, hypothesis: str) -> float:
    ref_chars = list(normalize_for_metrics(reference))
    hyp_chars = list(normalize_for_metrics(hypothesis))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    return _edit_distance(ref_chars, hyp_chars) / len(ref_chars)


def load_manifest(manifest_path: Path) -> list[BenchmarkSample]:
    if manifest_path.suffix.lower() == ".json":
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("JSON manifest must be an array of objects.")
        return [
            BenchmarkSample(
                audio_path=item["audio_path"],
                reference=item["reference"],
                sample_id=item.get("id") or Path(item["audio_path"]).stem,
            )
            for item in payload
        ]

    if manifest_path.suffix.lower() == ".csv":
        with manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                BenchmarkSample(
                    audio_path=row["audio_path"],
                    reference=row["reference"],
                    sample_id=row.get("id") or Path(row["audio_path"]).stem,
                )
                for row in reader
            ]

    raise ValueError("Manifest must be a .json or .csv file.")


def run_benchmark(samples: Iterable[BenchmarkSample]) -> dict:
    results = []
    total_wer = 0.0
    total_cer = 0.0
    exact_matches = 0
    sample_count = 0

    for sample in samples:
        prediction = transcribe_audio(sample.audio_path)
        wer = word_error_rate(sample.reference, prediction)
        cer = char_error_rate(sample.reference, prediction)
        exact = normalize_for_metrics(sample.reference) == normalize_for_metrics(prediction)
        exact_matches += int(exact)
        sample_count += 1
        total_wer += wer
        total_cer += cer
        results.append(
            {
                "id": sample.sample_id,
                "audio_path": sample.audio_path,
                "reference": sample.reference,
                "prediction": prediction,
                "wer": round(wer, 6),
                "cer": round(cer, 6),
                "exact_match": exact,
                "accuracy_estimate": round((1 - wer) * 100, 2),
            }
        )

    if sample_count == 0:
        raise ValueError("Manifest is empty.")

    avg_wer = total_wer / sample_count
    avg_cer = total_cer / sample_count
    return {
        "sample_count": sample_count,
        "average_wer": round(avg_wer, 6),
        "average_cer": round(avg_cer, 6),
        "accuracy_estimate": round((1 - avg_wer) * 100, 2),
        "exact_match_rate": round((exact_matches / sample_count) * 100, 2),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark transcription quality against labeled reference transcripts."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to a CSV or JSON manifest with audio_path, reference, and optional id.",
    )
    parser.add_argument(
        "--output",
        default="transcription_benchmark_results.json",
        help="Where to write the benchmark report JSON.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    samples = load_manifest(manifest_path)
    report = run_benchmark(samples)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Samples: {report['sample_count']}")
    print(f"Average WER: {report['average_wer']:.4f}")
    print(f"Average CER: {report['average_cer']:.4f}")
    print(f"Estimated accuracy: {report['accuracy_estimate']:.2f}%")
    print(f"Exact-match rate: {report['exact_match_rate']:.2f}%")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
