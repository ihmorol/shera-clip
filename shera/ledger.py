"""Paid-call journal and USD cap. Every paid provider call goes through call()."""
import json
import time

import httpx

from shera import config, db

PENDING = ("reserved", "sent", "indeterminate")


class BudgetStop(Exception):
    pass


class Indeterminate(Exception):
    pass


class ProviderError(Exception):
    """billed=True means the provider answered (and may have charged) but the answer was unusable."""

    def __init__(self, msg, billed=False, cost=None):
        super().__init__(msg)
        self.billed, self.cost = billed, cost


def spent(job_id):
    return db.one(
        "SELECT COALESCE(SUM(CASE WHEN state IN ('done','failed') THEN COALESCE(cost_usd,0) "
        "WHEN state='abandoned' THEN MAX(est_usd, COALESCE(cost_usd,0)) "
        "ELSE est_usd END), 0) AS s FROM paid_calls WHERE job_id=?", job_id)["s"]


def calls(job_id):
    return db.q("SELECT * FROM paid_calls WHERE job_id=? ORDER BY id", job_id)


def _observed(job_id, kind):
    return db.one("SELECT COALESCE(MAX(cost_usd), 0) AS m FROM paid_calls "
                  "WHERE job_id=? AND kind=? AND state='done'", job_id, kind)["m"]


def _finish(call_id, state, cost=None, result=None, error=None):
    db.x("UPDATE paid_calls SET state=?, cost_usd=?, result=?, error=?, updated=? WHERE id=?",
         state, cost, result, error, time.time(), call_id)


def call(job_id, key, kind, est_usd, fn):
    """Run fn() -> (result_dict, cost_or_None) at most once per (job, key), inside the budget."""
    with db.LOCK:
        row = db.one("SELECT * FROM paid_calls WHERE job_id=? AND key=? AND state!='abandoned'", job_id, key)
        if row and row["state"] == "done":
            return row["result"]
        if row and row["state"] in PENDING:
            raise Indeterminate(f"Paid call {key} may have been sent without a recorded answer. "
                                "Check the provider dashboard, then choose retry.")
        est = max(est_usd, _observed(job_id, kind))
        limit = min(db.get_job(job_id)["authorized_usd"] or 0, config.CAP_USD)
        used = spent(job_id)
        if used + est > limit + 1e-9:
            raise BudgetStop(f"Budget stop before {key}: ${used:.4f} spent + ${est:.4f} estimated "
                             f"would exceed the ${limit:.2f} limit. Partial work is kept.")
        now = time.time()
        if row and row["cost_usd"]:  # keep a billed failure counted; retry in a new row
            db.x("UPDATE paid_calls SET state='abandoned', updated=? WHERE id=?", now, row["id"])
            row = None
        if row:  # an unbilled failed call is retried in place
            call_id = row["id"]
            db.x("UPDATE paid_calls SET state='sent', est_usd=?, error=NULL, updated=? WHERE id=?", est, now, call_id)
        else:
            call_id = db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
                           "VALUES (?, ?, ?, 'sent', ?, ?, ?)", job_id, key, kind, est, now, now)
    try:
        result, cost = fn()
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:  # nothing reached the provider
        _finish(call_id, "failed", error=f"could not connect: {e}")
        raise ProviderError(f"{kind}: could not connect to provider ({e})") from e
    except httpx.HTTPStatusError as e:
        msg = f"{kind}: HTTP {e.response.status_code}: {e.response.text[:300]}"
        _finish(call_id, "failed", error=msg)
        raise ProviderError(msg) from e
    except ProviderError as e:
        cost = (est if e.cost is None else e.cost) if e.billed else None
        _finish(call_id, "failed", cost=cost, error=str(e))
        raise
    except Exception as e:
        _finish(call_id, "indeterminate", error=repr(e))
        raise Indeterminate(f"Paid call {key} was sent but its outcome is unknown ({e!r}). "
                            "Check the provider dashboard, then choose retry.") from e
    _finish(call_id, "done", cost=est if cost is None else cost, result=json.dumps(result, ensure_ascii=False))
    return result


def recover_on_start():
    db.x("UPDATE paid_calls SET state='indeterminate', updated=? WHERE state IN ('sent','reserved')", time.time())


def resolve(call_id):
    """Operator chose retry: the old call stays counted as possibly spent and the key is free."""
    db.x("UPDATE paid_calls SET state='abandoned', updated=? WHERE id=? AND state='indeterminate'",
         time.time(), call_id)
