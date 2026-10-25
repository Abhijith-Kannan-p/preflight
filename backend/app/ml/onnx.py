"""Shared ONNX Runtime set-up tuned for small hosts (Render free: 512 MB RAM, 0.1 CPU).

Measured on the int8 NLI model: graph optimisation expands the quantised weights at load
time (408 MiB resident vs 126 MiB with optimisation off), for identical outputs and about
20 % more latency. On a 512 MB host memory decides, so optimisation is off by default.
"""

from typing import Any

from app.config import get_settings


def lean_session(model_path: str) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False  # return memory between requests
    options.enable_mem_pattern = False
    options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
        if get_settings().onnx_optimize
        else ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    )
    return ort.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])
