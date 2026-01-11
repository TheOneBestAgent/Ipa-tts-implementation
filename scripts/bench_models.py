import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT_DIR / "pronouncex-tts"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from core.config import load_settings  # noqa: E402
from core.synth import Synthesizer  # noqa: E402


BENCH_TEXT = (
    "On the edge of the inlet, the morning light spilled across the tide and turned the "
    "harbor into a sheet of copper. A ferry slid out toward open water, its wake folding "
    "into the bay like a ribbon, while a market opened behind the docks and filled the air "
    "with the sound of carts, clinking bottles, and casual conversation. A musician tuned "
    "a violin under a striped awning, and a baker carried trays of bread into the breeze, "
    "smiling at the people who gathered for coffee. Inland, a slow train passed a schoolyard, "
    "a dog chased a rolling ball, and the city stretched from one street to the next with the "
    "steady rhythm of a place that knows how to wake up gently. Later in the day, clouds "
    "drifted in from the west, bringing a cool shadow that softened the heat and invited "
    "everyone back outside. Friends met on the boardwalk, swapping stories about the week, "
    "the distance of their travels, and the small surprises that made the season memorable. "
    "By evening the sky turned amber, the lights along the pier flickered on, and the water "
    "reflected a mosaic of warm colors. A quiet hum settled over the town, a mix of engines, "
    "laughter, and far-off music, and the night arrived with a calm confidence, as if the "
    "shoreline itself were breathing in time with the waves. The next morning brought a "
    "soft rain that tapped on windows and drew the smell of wet cedar up from the sidewalk, "
    "and the cafes filled with people drying their coats and trading news. In the library, "
    "a clerk arranged new books on a table while a student marked a map with careful lines, "
    "planning a weekend hike along the ridge. When the rain cleared, the air felt bright and "
    "clean, and a line of cyclists drifted past the park, their bells chiming like small "
    "instruments. Somewhere near the river, a gardener clipped lavender and stacked the stems "
    "in a basket, and the scent followed her as she crossed the bridge. At the waterfront, "
    "a group practiced rowing in perfect cadence, the oars lifting and falling with an easy "
    "discipline. The evening market returned with lanterns and fresh fruit, and a vendor told "
    "a story about the storms that once reshaped the shoreline. By nightfall the clouds broke "
    "into stars, and the town fell quiet again, as if the entire coast were listening to the "
    "tide and keeping time with its patient rhythm."
)
WARMUP_TEXT = (
    "This is a longer warmup sentence to avoid very short input edge cases in some models."
)


def _parse_model_ids(models_arg: str | None) -> List[str]:
    if models_arg:
        items = [item.strip() for item in models_arg.split(",") if item.strip()]
        if not items:
            raise ValueError("No models provided in --models")
        return items
    settings = load_settings()
    return settings.model_allowlist


def _run_benchmarks(model_ids: Iterable[str]) -> Tuple[int, List[Tuple[str, float, float]]]:
    text_chars = len(BENCH_TEXT)
    results = []
    failures = 0

    for model_id in model_ids:
        try:
            synthesizer = Synthesizer(model_id)
            synthesizer.synthesize(WARMUP_TEXT, None)
            start = time.perf_counter()
            synthesizer.synthesize(BENCH_TEXT, None)
            total = time.perf_counter() - start
        except Exception as exc:
            print(f"{model_id}: error {exc}")
            failures += 1
            continue
        chars_per_sec = text_chars / total if total > 0 else 0.0
        results.append((model_id, total, chars_per_sec))
        print(f"{model_id}: {total:.2f}s, {chars_per_sec:.1f} chars/sec")

    return failures, results


def benchmark_models(models_arg: str | None) -> int:
    try:
        model_ids = _parse_model_ids(models_arg)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    failures, results = _run_benchmarks(model_ids)

    if not results:
        print("No models benchmarked successfully.")
        return 1

    print("\nRanking (fastest first):")
    for rank, (model_id, total, chars_per_sec) in enumerate(
        sorted(results, key=lambda item: item[1]), start=1
    ):
        print(f"{rank}. {model_id}: {total:.2f}s, {chars_per_sec:.1f} chars/sec")

    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Coqui TTS models.")
    parser.add_argument(
        "--models",
        help="Comma-separated model ids. Defaults to PRONOUNCEX_TTS_MODEL_ALLOWLIST.",
    )
    args = parser.parse_args()
    raise SystemExit(benchmark_models(args.models))
