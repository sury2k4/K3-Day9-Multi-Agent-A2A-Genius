import json
import pytest
from olist_disputes.runner import load_cases

def test_batch_requires_exact_fifty(tmp_path):
    with pytest.raises(RuntimeError, match="exactly 50"):
        load_cases(tmp_path)

def test_batch_rejects_wrong_case_id(tmp_path):
    for i in range(1, 51):
        (tmp_path / f"EC_{i:03d}.json").write_text(json.dumps({"case_id": f"EC_{i:03d}", "opened_at": "2018-10-18T00:00:00", "customer_request": {"language": "vi", "message": "x", "claimed_order_id": "o"}, "policy_version": "EC_POLICY_V1"}))
    (tmp_path / "EC_001.json").write_text(json.dumps({"case_id": "EC_999", "opened_at": "2018-10-18T00:00:00", "customer_request": {"language": "vi", "message": "x", "claimed_order_id": "o"}, "policy_version": "EC_POLICY_V1"}))
    with pytest.raises(ValueError):
        load_cases(tmp_path)
