from .graph import run_case


def deterministic_fallback(case, data_dir, trace=None):
    """Run source-owned path; model availability never changes financial output."""
    return run_case(case, data_dir, llm=None, trace=trace)
