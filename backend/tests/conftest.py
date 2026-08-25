"""Session-wide test setup.

faisslite (via faiss-cpu) and krutrim_agent_doc's docling parsers (via
torch) can both load into this one pytest process across different test
modules, and each links its own bundled OpenMP runtime. Loading both
natively aborts the process on macOS ("OMP: Error #15") unless
KMP_DUPLICATE_LIB_OK is set before either is first imported — but that alone
only silences the duplicate-init *check*; two OpenMP thread pools actually
running concurrently in one process can still segfault (observed running
the full suite, not just test_embeddings.py in isolation). Pinning both
libraries to a single thread removes the concurrent-execution case that
triggers it. Must be the first thing this file does, ahead of any test
module import that could pull in faiss or torch.
"""

from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

try:
    import faiss

    faiss.omp_set_num_threads(1)
except ImportError:
    pass
