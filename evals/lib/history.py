"""Write made-up GitHub Actions run history in the shape measure.py fetch saves.

Used once to author each sample repository's ci-history/. The data is
invented for the evals; it describes no real repository.
"""
import json
import random
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def job(jid, name, created, wait, steps, conclusion="success", attempt=1, labels=("ubuntu-latest",)):
    """steps: list of (name, seconds[, conclusion])."""
    start = created + timedelta(seconds=wait)
    t = start
    out = []
    for s in steps:
        sname, sec = s[0], s[1]
        sc = s[2] if len(s) > 2 else "success"
        out.append({"name": sname, "conclusion": sc, "started_at": iso(t),
                    "completed_at": iso(t + timedelta(seconds=sec))})
        t += timedelta(seconds=sec)
    return {"id": jid, "name": name, "run_attempt": attempt, "conclusion": conclusion,
            "created_at": iso(created), "started_at": iso(start), "completed_at": iso(t),
            "labels": list(labels), "runner_name": "GitHub Actions %d" % (jid % 50), "steps": out}


def run(rid, created, jobs, name="CI", event="pull_request", branch="feature", sha=None,
        conclusion="success", attempt=1, prs=(1,)):
    end = max(j["completed_at"] for j in jobs)
    return {"id": rid, "name": name, "path": ".github/workflows/ci.yml", "event": event,
            "head_branch": branch, "head_sha": sha or ("%040x" % rid), "run_attempt": attempt,
            "conclusion": conclusion, "created_at": iso(created), "run_started_at": iso(created),
            "updated_at": end, "pull_requests": list(prs), "jobs": jobs}


def write(path, runs):
    with open(path, "w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")


def jitter(rng, x, frac=0.08):
    return max(1, int(x * (1 + rng.uniform(-frac, frac))))
