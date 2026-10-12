"""Read-only four-context GenieX QNN graph inventory on VENTUNO Q.

Inspects one bounded cache bundle sequentially with Qualcomm's metadata-only
utility. No qnn-net-run, inference, model reload, service changes, or persistent
model copies. Public CI output deliberately excludes names, paths and raw JSON.
Graph order in metadata is NOT asserted to be GenieX execution/load order.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, deque
from pathlib import Path

try:
    import resource
except ImportError:
    resource = None

MAX_DIRS = 100
MAX_FILES = 300
MAX_CONTEXTS = 4
MAX_BINARY_BYTES = 1100 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MIN_AVAILABLE_KIB = 3 * 1024 * 1024
TOOL_TIMEOUT = 25


def find_bundle(roots: tuple[Path, ...]) -> tuple[list[Path], list[Path], str]:
    """Reject partial or ambiguous caches; don't follow symlinks."""
    pending = deque((root, 0) for root in roots
                    if root.is_dir() and not root.is_symlink())
    binaries: list[Path] = []
    manifests: list[Path] = []
    directories = files = 0
    while pending and directories < MAX_DIRS and files < MAX_FILES:
        folder, depth = pending.popleft()
        directories += 1
        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except OSError:
            return [], [], "inconclusive-unreadable-directory"
        for entry in entries:
            if files >= MAX_FILES:
                break
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < 5:
                        pending.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                files += 1
                if entry.name.endswith(".bin"):
                    if not 0 < entry.stat(follow_symlinks=False).st_size <= MAX_BINARY_BYTES:
                        return [], [], "no-go-unbounded-binary"
                    binaries.append(Path(entry.path))
                elif entry.name == "geniex.json":
                    if entry.stat(follow_symlinks=False).st_size > 131072:
                        return [], [], "no-go-unbounded-manifest"
                    manifests.append(Path(entry.path))
            except OSError:
                return [], [], "inconclusive-file-inspection"
    if pending or files >= MAX_FILES:
        return [], [], "inconclusive-scan-capped"
    if len(binaries) != MAX_CONTEXTS or len(manifests) != 1:
        return [], [], "inconclusive-bundle-count"
    # An inventory slot is determined only by size/path sort, NEVER load order.
    binaries.sort(key=lambda p: (p.stat().st_size, str(p)))
    return binaries, manifests, "bundle-candidates-found"


def read_memory_kib() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def manifest_refs(data: object) -> list[str]:
    """Extract only ordered .bin basenames from allowlisted manifest entries.

    Neither ExtraFiles order nor ModelFile order proves runtime load order.
    """
    if not isinstance(data, dict):
        return []
    refs: list[str] = []
    def collect(value: object, depth: int = 0) -> None:
        if depth > 3 or len(refs) >= 20:
            return
        if isinstance(value, str):
            if value.lower().endswith(".bin") and not value.startswith(("http:", "https:")):
                refs.append(Path(value.replace("\\", "/")).name)
        elif isinstance(value, list):
            for item in value[:20]:
                collect(item, depth + 1)
        elif isinstance(value, dict):
            for item in list(value.values())[:20]:
                collect(item, depth + 1)
    for key in ("ModelFile", "ExtraFiles"):
        collect(data.get(key))
    return refs


def manifest_reference_summary(data: object, binaries: list[Path]) -> dict[str, object]:
    refs = manifest_refs(data)
    slots: list[int] = []
    for ref in refs:
        matched = [i for i, path in enumerate(binaries) if path.name == ref]
        if len(matched) == 1 and matched[0] not in slots:
            slots.append(matched[0])
    return {
        "manifest_bin_reference_count": len(refs),
        "matched_candidate_slots": slots,
        "covers_all_contexts": len(slots) == len(binaries) and len(refs) == len(binaries),
        "runtime_order_proven": False,
    }


def context_order_from_genie_config(
    config: object, config_dir: Path, binaries: list[Path]
) -> dict[str, object]:
    """Resolve ctx-bins declarations against exact relative cache paths.

    This matches Qualcomm's documented modelConfigFromDirectory path, but
    does not assert which loader version the running process actually used.
    """
    result: dict[str, object] = {
        "status": "no-verified-context-order",
        "declared_inventory_slots": [],
        "complete_ctx_bin_reference_list": False,
        "runtime_load_order_proven": False,
    }
    if not isinstance(config, dict):
        return result
    dialog = config.get("dialog")
    if not isinstance(dialog, dict):
        return result
    engine = dialog.get("engine")
    if isinstance(engine, list):
        candidates = [item for item in engine if isinstance(item, dict)]
        if not candidates:
            return result
        targets = [item for item in candidates if item.get("role") == "target"]
        if len(targets) > 1:
            return result
        engine = targets[0] if targets else candidates[0]
    if not isinstance(engine, dict):
        return result
    model = engine.get("model")
    binary = model.get("binary") if isinstance(model, dict) else None
    refs = binary.get("ctx-bins") if isinstance(binary, dict) else None
    if not isinstance(refs, list) or not refs or len(refs) > MAX_CONTEXTS:
        return result
    resolved = []
    for ref in refs:
        if (not isinstance(ref, str) or not ref.endswith(".bin")
                or len(ref) > 255 or ref.startswith(("/", "\\\\"))
                or "\\" in ref or ".." in Path(ref).parts):
            return result
        matches = [
            slot for slot, candidate in enumerate(binaries)
            if candidate.is_relative_to(config_dir)
            and candidate.relative_to(config_dir).as_posix() == ref
        ]
        if len(matches) != 1 or matches[0] in resolved:
            return result
        resolved.append(matches[0])
    result.update({
        "status": "complete-declared-order" if len(resolved) == len(binaries)
                  else "partial-declared-order",
        "declared_inventory_slots": resolved,
        "complete_ctx_bin_reference_list": len(resolved) == len(binaries),
    })
    return result


def inspect_genie_config(binaries: list[Path]) -> dict[str, object]:
    parents = {p.parent for p in binaries}
    if len(parents) != 1:
        return {"status": "inconclusive-context-directories",
                "runtime_load_order_proven": False}
    config_dir = next(iter(parents))
    config_path = config_dir / "genie_config.json"
    if not config_path.is_file() or config_path.is_symlink():
        return {"status": "no-genie-config-found",
                "runtime_load_order_proven": False}
    try:
        if config_path.stat().st_size > 131072:
            return {"status": "inconclusive-config-too-large",
                    "runtime_load_order_proven": False}
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {"status": "inconclusive-config-unreadable",
                "runtime_load_order_proven": False}
    return context_order_from_genie_config(config, config_dir, binaries)


def graph_info(graph: object, position: int) -> tuple[dict[str, object], set[tuple]]:
    data = graph.get("info") if isinstance(graph, dict) else None
    if not isinstance(data, dict):
        return {"metadata_index": position, "status": "invalid"}, (set(), set())
    name = data.get("graphName")
    # Hash is used only to correlate graph metadata; never log raw names.
    token = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12] if (
        isinstance(name, str) and 0 < len(name) <= 256
    ) else None
    inputs = data.get("graphInputs")
    outputs = data.get("graphOutputs")
    def signatures(items: object) -> set[tuple]:
        if not isinstance(items, list) or len(items) > 80:
            return set()
        result = set()
        for item in items:
            tensor = item.get("info") if isinstance(item, dict) else None
            if not isinstance(tensor, dict):
                continue
            tensor_name = tensor.get("name")
            dtype = tensor.get("dataType")
            dims = tensor.get("dimensions")
            if (isinstance(tensor_name, str) and len(tensor_name) <= 256
                    and isinstance(dtype, str) and len(dtype) <= 90
                    and isinstance(dims, list) and 1 <= len(dims) <= 8
                    and all(type(x) is int and 0 < x <= 10000000 for x in dims)):
                result.add((tensor_name, dtype, tuple(dims)))
        return result
    output_signatures = signatures(outputs)
    input_signatures = signatures(inputs)
    return {
        "metadata_index": position,
        "graph_token": token,
        "input_count": len(inputs) if isinstance(inputs, list) else None,
        "output_count": len(outputs) if isinstance(outputs, list) else None,
        "input_signature_count": len(input_signatures),
        "output_signature_count": len(output_signatures),
        "runtime_slot_proven": False,
    }, (input_signatures, output_signatures)


def summarize_graphs(data: object) -> tuple[dict[str, object], list[tuple[set, set]]]:
    info = data.get("info") if isinstance(data, dict) else None
    graphs = info.get("graphs") if isinstance(info, dict) else None
    if not isinstance(graphs, list) or len(graphs) > 24:
        return {"status": "inconclusive-graph-list"}, []
    summaries = []
    signatures = []
    for index, graph in enumerate(graphs):
        row, pairs = graph_info(graph, index)
        summaries.append(row)
        signatures.append(pairs)
    return {
        "status": "metadata-read",
        "graph_count": len(graphs),
        "graphs": summaries,
        "metadata_order_not_runtime_order": True,
    }, signatures


def overlap_counts(contexts: list[list[tuple[set, set]]]) -> list[dict[str, int]]:
    """Potential IO-name matches only, not proven runtime dependencies."""
    summaries = []
    for source, source_graphs in enumerate(contexts):
        for target, target_graphs in enumerate(contexts):
            if source == target:
                continue
            count = sum(len(out & inp) for _, out in source_graphs
                        for inp, _ in target_graphs)
            if count:
                summaries.append({
                    "source_inventory_slot": source,
                    "target_inventory_slot": target,
                    "matching_io_signatures": count,
                })
    return summaries


def _child_limits() -> None:
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (5 * 1024**2, 5 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def inspect_context(binary: Path, tmp_root: Path) -> tuple[dict[str, object], list]:
    utility = shutil.which("qnn-context-binary-utility")
    if not utility:
        return {"status": "inconclusive-utility-unavailable"}, []
    if read_memory_kib() < MIN_AVAILABLE_KIB:
        return {"status": "inconclusive-insufficient-memory"}, []
    with tempfile.TemporaryDirectory(prefix="myai-context-map-", dir=tmp_root) as temp:
        output = Path(temp) / "metadata.json"
        with open(os.devnull, "wb") as sink:
            try:
                result = subprocess.run(
                    [utility, "--context_binary", str(binary),
                     "--json_file", str(output)],
                    cwd=temp, stdout=sink, stderr=subprocess.STDOUT,
                    timeout=TOOL_TIMEOUT, check=False,
                    preexec_fn=_child_limits if resource is not None else None,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return {"status": "inconclusive-utility-error",
                        "error_type": type(exc).__name__}, []
        if result.returncode:
            return {"status": "inconclusive-utility-exit"}, []
        try:
            if not output.is_file() or output.stat().st_size > MAX_JSON_BYTES:
                return {"status": "inconclusive-output-size"}, []
            data = json.loads(output.read_text(errors="replace"))
        except (OSError, ValueError):
            return {"status": "inconclusive-metadata-json"}, []
        return summarize_graphs(data)


def main() -> int:
    home = Path.home()
    roots = (home / ".cache" / "geniex",
             home / ".local" / "share" / "geniex" / "models",
             home / ".local" / "share" / "geniex" / "cache")
    binaries, manifests, status = find_bundle(roots)
    print("GenieX QNN multi-context metadata inventory (read-only)")
    if status != "bundle-candidates-found":
        print(json.dumps({"status": status, "runtime_order_proven": False}))
        return 0
    tmp = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    if not tmp.is_dir() or tmp.is_symlink():
        print(json.dumps({"status": "inconclusive-temporary-directory"}))
        return 0
    try:
        manifest_data = json.loads(manifests[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest_data = None
    print("Manifest references:", json.dumps(
        manifest_reference_summary(manifest_data, binaries), sort_keys=True))
    print("Genie ctx-bin order declaration:", json.dumps(
        inspect_genie_config(binaries), sort_keys=True))
    all_signatures = []
    completed = 0
    for slot, binary in enumerate(binaries):
        report, signatures = inspect_context(binary, tmp)
        if report.get("status") == "metadata-read":
            completed += 1
        all_signatures.append(signatures)
        print("Context:", json.dumps({
            "inventory_slot": slot,
            "binary_size_mib": round(binary.stat().st_size / 1048576, 1),
            **report,
        }, sort_keys=True))
    print("Cross-context signature overlaps:", json.dumps(
        overlap_counts(all_signatures), sort_keys=True))
    print("Summary:", json.dumps({
        "contexts_with_metadata": completed,
        "context_count": len(binaries),
        "graph_execution_order_proven": False,
        "inter_context_dependencies_proven": False,
        "direct_npu_profile_verified": False,
        "safe_to_start_second_model": False,
        "services_changed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
