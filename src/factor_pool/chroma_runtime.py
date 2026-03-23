"""Chroma/ONNX runtime helpers for FactorPool."""

from __future__ import annotations

import ctypes
import importlib
import logging
import os
import sysconfig
from contextlib import contextmanager
from pathlib import Path

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


logger = logging.getLogger(__name__)

_ONNX_RUNTIME_BOOTSTRAPPED = False


def _is_wsl_runtime() -> bool:
    if os.getenv("WSL_INTEROP") or os.getenv("WSL_DISTRO_NAME"):
        return True
    proc_version = Path("/proc/version")
    try:
        return "microsoft" in proc_version.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _should_quiet_onnxruntime_import() -> bool:
    raw = os.getenv("PIXIU_SUPPRESS_ONNXRUNTIME_IMPORT_WARNING", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return _is_wsl_runtime()


@contextmanager
def _suppress_stderr_fd():
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    stderr_fd = os.dup(2)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        os.close(devnull_fd)


def _import_onnxruntime():
    if not _should_quiet_onnxruntime_import():
        return importlib.import_module("onnxruntime")
    with _suppress_stderr_fd():
        return importlib.import_module("onnxruntime")


def _candidate_nvidia_library_dirs() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    for key in ("purelib", "platlib"):
        base = sysconfig.get_paths().get(key)
        if not base:
            continue

        site_packages = Path(base)
        for relative_dir in ("nvidia/cudnn/lib", "nvidia/cublas/lib"):
            candidate = site_packages / relative_dir
            if candidate.is_dir() and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)

    return candidates


def _shared_library_candidates(lib_dir: Path) -> list[Path]:
    lib_dir_str = str(lib_dir)
    if "/nvidia/cudnn/lib" in lib_dir_str:
        return sorted(lib_dir.glob("libcudnn*.so*"))
    if "/nvidia/cublas/lib" in lib_dir_str:
        ordered: list[Path] = []
        for pattern in ("libcublasLt.so*", "libcublas.so*", "libnvblas.so*"):
            ordered.extend(sorted(lib_dir.glob(pattern)))
        return ordered
    return []


def _load_shared_library(path: Path) -> bool:
    try:
        ctypes.CDLL(str(path), mode=getattr(ctypes, "RTLD_GLOBAL", 0))
        return True
    except OSError as exc:
        logger.debug("Failed to preload shared library %s: %s", path, exc)
        return False


def bootstrap_onnx_runtime() -> None:
    """Preload pip-installed NVIDIA runtime libraries before importing ORT."""
    global _ONNX_RUNTIME_BOOTSTRAPPED

    if _ONNX_RUNTIME_BOOTSTRAPPED:
        return

    library_dirs = _candidate_nvidia_library_dirs()
    if not library_dirs:
        return

    loaded_count = 0
    for lib_dir in library_dirs:
        for shared_library in _shared_library_candidates(lib_dir):
            if _load_shared_library(shared_library):
                loaded_count += 1

    if loaded_count:
        logger.info(
            "[FactorPool] 预加载 NVIDIA runtime libraries：%d 个共享库",
            loaded_count,
        )

    _ONNX_RUNTIME_BOOTSTRAPPED = True


def _select_preferred_onnx_providers(available_providers: list[str]) -> list[str]:
    preferred: list[str] = []

    if "CUDAExecutionProvider" in available_providers:
        preferred.append("CUDAExecutionProvider")
    if "CPUExecutionProvider" in available_providers:
        preferred.append("CPUExecutionProvider")

    if preferred:
        return preferred

    non_tensorrt = [
        provider
        for provider in available_providers
        if provider != "TensorrtExecutionProvider"
    ]
    return non_tensorrt or list(available_providers)


class _PreferredONNXEmbeddingFunction(EmbeddingFunction[Documents]):
    """Chroma embedding function with stable ONNX provider ordering."""

    def __init__(self, preferred_providers: list[str]) -> None:
        self._preferred_providers = list(preferred_providers)

    def __call__(self, input: Documents) -> Embeddings:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import (
            ONNXMiniLM_L6_V2,
        )

        return ONNXMiniLM_L6_V2(preferred_providers=self._preferred_providers)(input)

    def embed_query(self, input: Documents) -> Embeddings:
        return self(input)

    @staticmethod
    def build_from_config(
        config: dict[str, object],
    ) -> "_PreferredONNXEmbeddingFunction":
        providers = config.get("preferred_providers")
        if isinstance(providers, list) and all(
            isinstance(provider, str) for provider in providers
        ):
            return _PreferredONNXEmbeddingFunction(providers)
        return _PreferredONNXEmbeddingFunction([])

    @staticmethod
    def name() -> str:
        return "pixiu_default_onnx"

    def get_config(self) -> dict[str, object]:
        return {"preferred_providers": list(self._preferred_providers)}

    def max_tokens(self) -> int:
        return 256

    @staticmethod
    def validate_config(config: dict[str, object]) -> None:
        return


def build_default_chroma_embedding_function() -> EmbeddingFunction[Documents]:
    """Build the default Chroma embedding function with stable provider order."""
    bootstrap_onnx_runtime()

    ort = _import_onnxruntime()

    preferred_providers = _select_preferred_onnx_providers(
        ort.get_available_providers()
    )
    return _PreferredONNXEmbeddingFunction(preferred_providers)
