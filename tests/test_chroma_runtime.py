"""Unit tests for Chroma runtime helpers."""

from pathlib import Path

import pytest

from src.factor_pool import chroma_runtime

pytestmark = pytest.mark.unit


def test_select_preferred_onnx_providers_prefers_cuda_then_cpu():
    providers = [
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]

    assert chroma_runtime._select_preferred_onnx_providers(providers) == [
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]


def test_select_preferred_onnx_providers_falls_back_to_cpu():
    providers = ["CPUExecutionProvider"]

    assert chroma_runtime._select_preferred_onnx_providers(providers) == [
        "CPUExecutionProvider",
    ]


def test_build_default_chroma_embedding_function_is_not_default_embedding_subclass(monkeypatch):
    class _FakeOrt:
        @staticmethod
        def get_available_providers():
            return ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]

    monkeypatch.setattr(chroma_runtime, "bootstrap_onnx_runtime", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", _FakeOrt)

    embedding_function = chroma_runtime.build_default_chroma_embedding_function()

    assert embedding_function.__class__.__name__ == "_PreferredONNXEmbeddingFunction"
    assert getattr(embedding_function, "_preferred_providers") == [
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]


def test_bootstrap_onnx_runtime_preloads_nvidia_runtime_libs(tmp_path, monkeypatch):
    purelib = tmp_path / "site-packages"
    cudnn_dir = purelib / "nvidia" / "cudnn" / "lib"
    cublas_dir = purelib / "nvidia" / "cublas" / "lib"
    cudnn_dir.mkdir(parents=True)
    cublas_dir.mkdir(parents=True)

    for filename in (
        "libcudnn.so.9",
        "libcublasLt.so.12",
        "libcublas.so.12",
    ):
        target_dir = cudnn_dir if "cudnn" in filename else cublas_dir
        (target_dir / filename).write_text("", encoding="utf-8")

    loaded: list[str] = []

    monkeypatch.setattr(chroma_runtime, "_ONNX_RUNTIME_BOOTSTRAPPED", False)
    monkeypatch.setattr(
        chroma_runtime.sysconfig,
        "get_paths",
        lambda: {"purelib": str(purelib), "platlib": str(purelib)},
    )
    monkeypatch.setattr(
        chroma_runtime.ctypes,
        "CDLL",
        lambda path, mode=0: loaded.append(Path(path).name),
    )

    chroma_runtime.bootstrap_onnx_runtime()
    chroma_runtime.bootstrap_onnx_runtime()

    assert loaded == [
        "libcudnn.so.9",
        "libcublasLt.so.12",
        "libcublas.so.12",
    ]
