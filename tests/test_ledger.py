import httpx
import pytest

from shera import config, db, ledger


class Crash(BaseException):
    """Simulates the process dying mid-call (not caught like an ordinary error)."""


@pytest.fixture
def job(tmp_path):
    config.set_data(tmp_path)
    db.init()
    db.x("INSERT INTO jobs(id, status, authorized_usd, flags) VALUES ('j', 'running', 1.5, '[]')")
    return "j"


def fake(result=None, cost=0.01, calls=None, exc=None):
    def fn():
        if calls is not None:
            calls.append(1)
        if exc:
            raise exc
        return result or {"ok": True}, cost
    return fn


def state(job, key):
    return db.one("SELECT state FROM paid_calls WHERE job_id=? AND key=? AND state!='abandoned'", job, key)["state"]


def test_done_call_is_never_replayed(job):
    calls = []
    assert ledger.call(job, "jev:1", "jev", 0.002, fake({"v": 3}, 0.01, calls)) == {"v": 3}
    assert ledger.call(job, "jev:1", "jev", 0.002, fake({"v": 0}, 0.01, calls)) == {"v": 3}
    assert len(calls) == 1
    assert ledger.spent(job) == pytest.approx(0.01)


def test_missing_cost_records_estimate(job):
    ledger.call(job, "k", "draft", 0.002, fake(cost=None))
    assert ledger.spent(job) == pytest.approx(0.002)


def test_budget_stop_before_sending(job):
    calls = []
    db.update_job(job, authorized_usd=0.01)
    with pytest.raises(ledger.BudgetStop):
        ledger.call(job, "k", "jev", 0.02, fake(calls=calls))
    assert calls == [] and ledger.calls(job) == []


def test_budget_is_capped_at_cap_usd_even_if_more_authorized(job):
    db.update_job(job, authorized_usd=5.0)
    ledger.call(job, "a", "whisper", 1.0, fake(cost=1.0))
    with pytest.raises(ledger.BudgetStop):
        ledger.call(job, "b", "draft", 0.6, fake(cost=0.6))
    ledger.call(job, "c", "jev", 0.5, fake(cost=0.5))  # exactly at the cap is allowed
    assert ledger.spent(job) == pytest.approx(1.5)


def test_unauthorized_job_cannot_spend(job):
    db.update_job(job, authorized_usd=None)
    with pytest.raises(ledger.BudgetStop):
        ledger.call(job, "k", "jev", 0.002, fake())


def test_crash_leaves_sent_then_recover_makes_indeterminate_and_blocks_key(job):
    with pytest.raises(Crash):
        ledger.call(job, "k", "jev", 0.002, fake(exc=Crash()))
    assert state(job, "k") == "sent"
    ledger.recover_on_start()
    assert state(job, "k") == "indeterminate"
    calls = []
    with pytest.raises(ledger.Indeterminate):
        ledger.call(job, "k", "jev", 0.002, fake(calls=calls))
    assert calls == []
    assert ledger.spent(job) == pytest.approx(0.002)


def test_timeout_after_send_is_indeterminate(job):
    with pytest.raises(ledger.Indeterminate):
        ledger.call(job, "k", "jev", 0.002, fake(exc=httpx.ReadTimeout("slow")))
    assert state(job, "k") == "indeterminate"


def test_resolve_abandons_keeps_estimate_counted_and_frees_key(job):
    with pytest.raises(ledger.Indeterminate):
        ledger.call(job, "k", "jev", 0.002, fake(exc=RuntimeError("boom")))
    row = ledger.calls(job)[0]
    ledger.resolve(row["id"])
    assert ledger.calls(job)[0]["state"] == "abandoned"
    assert ledger.spent(job) == pytest.approx(0.002)
    assert ledger.call(job, "k", "jev", 0.002, fake({"v": 1}, 0.003)) == {"v": 1}
    assert ledger.spent(job) == pytest.approx(0.005)


def test_connect_error_is_failed_and_retryable(job):
    with pytest.raises(ledger.ProviderError):
        ledger.call(job, "k", "jev", 0.002, fake(exc=httpx.ConnectError("down")))
    assert state(job, "k") == "failed"
    assert ledger.spent(job) == 0
    assert ledger.call(job, "k", "jev", 0.002, fake({"v": 2}, 0.001)) == {"v": 2}
    assert state(job, "k") == "done"


def test_http_error_response_is_failed_with_error(job):
    req = httpx.Request("POST", "https://example.invalid")
    err = httpx.HTTPStatusError("bad", request=req, response=httpx.Response(429, text="rate limited", request=req))
    with pytest.raises(ledger.ProviderError, match="429"):
        ledger.call(job, "k", "jev", 0.002, fake(exc=err))
    row = ledger.calls(job)[0]
    assert row["state"] == "failed" and "rate limited" in row["error"]


def test_billed_bad_answer_counts_cost(job):
    with pytest.raises(ledger.ProviderError):
        ledger.call(job, "k", "draft", 0.002, fake(exc=ledger.ProviderError("bad shape", billed=True, cost=0.004)))
    assert ledger.spent(job) == pytest.approx(0.004)


def test_observed_cost_raises_estimate(job):
    for k in ("a", "b", "c"):
        ledger.call(job, k, "jev", 0.002, fake(cost=0.5))
    calls = []
    with pytest.raises(ledger.BudgetStop):  # config est 0.002 would fit; observed 0.5 does not
        ledger.call(job, "d", "jev", 0.002, fake(calls=calls))
    assert calls == []
    db.update_job(job, authorized_usd=1.5)
    db.x("UPDATE paid_calls SET cost_usd=0.1 WHERE key IN ('a','b')")  # spent 0.7, max observed 0.5
    ledger.call(job, "d", "jev", 0.002, fake(cost=None))
    assert ledger.calls(job)[-1]["est_usd"] == pytest.approx(0.5)
    assert ledger.calls(job)[-1]["cost_usd"] == pytest.approx(0.5)


def test_retry_after_billed_failure_keeps_first_cost(job):
    def bad():
        raise ledger.ProviderError("bad shape", billed=True, cost=0.05)
    with pytest.raises(ledger.ProviderError):
        ledger.call(job, "k", "draft", 0.01, bad)
    ledger.call(job, "k", "draft", 0.01, lambda: ({"ok": 1}, 0.02))
    assert abs(ledger.spent(job) - 0.07) < 1e-9
