#!/usr/bin/env python3
"""Repository checks: skill format, copies in step, links, and a generic leak scan.

Run from the repository root: python3 tools/check.py
Standard library only. Exits non-zero on any failure.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ALLOWED_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RULES_RE = re.compile(r"<!-- rules:start -->.*?<!-- rules:end -->", re.S)
errors = []


def err(msg):
    errors.append(msg)


def frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    raw = text[4:end]
    fields, current = {}, None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if current is None:
                return None, text
            fields[current] += "\n" + line
            continue
        if ":" not in line:
            return None, text
        k, v = line.split(":", 1)
        current = k.strip()
        fields[current] = v.strip()
    return fields, text[end + 5:]


def check_skills():
    skills = sorted(glob.glob("skills/*/SKILL.md"))
    if not skills:
        err("no skills found")
    measure = open("skills/ci-measure/scripts/measure.py").read()
    rules = RULES_RE.search(open("snippets/AGENTS.md").read())
    if not rules:
        err("snippets/AGENTS.md has no rules block")
    for path in skills:
        d = os.path.basename(os.path.dirname(path))
        text = open(path).read()
        fm, body = frontmatter(text)
        if fm is None:
            err("%s: missing or malformed frontmatter" % path)
            continue
        extra = set(fm) - ALLOWED_FIELDS
        if extra:
            err("%s: non-standard fields %s" % (path, sorted(extra)))
        name = fm.get("name", "")
        if name != d:
            err("%s: name %r doesn't match folder %r" % (path, name, d))
        if not NAME_RE.match(name) or len(name) > 64:
            err("%s: bad name %r" % (path, name))
        desc = fm.get("description", "")
        if not desc or len(desc) > 1024:
            err("%s: description empty or over 1024 characters (%d)" % (path, len(desc)))
        if ": " in desc or desc.endswith(":") or " #" in desc or desc[:1] in "\"'[{&*!|>%@`":
            err("%s: description isn't a plain YAML scalar; strict parsers will reject it" % path)
        if len(fm.get("compatibility", "")) > 500:
            err("%s: compatibility over 500 characters" % path)
        if len(text.splitlines()) > 500:
            err("%s: over 500 lines" % path)
        m = RULES_RE.search(text)
        if not m or not rules or m.group(0) != rules.group(0):
            err("%s: rules block differs from snippets/AGENTS.md" % path)
        mp = os.path.join(os.path.dirname(path), "scripts", "measure.py")
        if "measure.py" in body:
            if not os.path.exists(mp):
                err("%s: mentions measure.py but has no scripts/measure.py" % path)
            elif open(mp).read() != measure:
                err("%s differs from skills/ci-measure/scripts/measure.py" % mp)
        ev = os.path.join(os.path.dirname(path), "references", "evidence.md")
        if not os.path.exists(ev):
            err("%s: no references/evidence.md" % path)
        for ref in re.findall(r"`(references/[\w.-]+|scripts/[\w.-]+)`", body):
            if not os.path.exists(os.path.join(os.path.dirname(path), ref)):
                err("%s: refers to missing %s" % (path, ref))
    guide = open("skills/ci-measure/references/measuring.md").read()
    for g in glob.glob("skills/*/references/measuring.md"):
        if open(g).read() != guide:
            err("%s differs from skills/ci-measure/references/measuring.md" % g)
    for d in glob.glob("skills/*/"):
        if not os.path.exists(d + "references/measuring.md"):
            err("%s has no references/measuring.md" % d)
    snippet = "skills/ci-guard/references/agents-snippet.md"
    if open(snippet).read() != open("snippets/AGENTS.md").read():
        err("%s differs from snippets/AGENTS.md" % snippet)


def check_evidence():
    for path in glob.glob("skills/*/references/evidence.md"):
        for line in open(path):
            if not line.startswith("| [") :
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not re.match(r"^\[.+\]\(https://[^)\s]+\)$", cells[0]):
                err("%s: source cell needs one https link: %s" % (path, cells[0][:60]))
            if cells[-1] not in ("A", "B", "C", "D"):
                err("%s: grade must be A-D: %s" % (path, cells[-1]))


# A generic leak scan. The private deny-list stays private; this catches the
# shapes that must never appear in a public file.
LEAKS = [
    (re.compile(r"\bORG-\d"), "anonymised org label"),
    (re.compile(r"\bP-\d\b"), "anonymised person label"),
    (re.compile(r"/Users/[a-z]"), "a local home path"),
    (re.compile(r"/home/[a-z][a-z0-9_-]*/"), "a local home path"),
    (re.compile(r"\b(ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"), "a GitHub token"),
    (re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}"), "an API key"),
    (re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "a private IP address"),
    (re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"), "a private IP address"),
    (re.compile(r"\b[\w.+-]+@(?!example\.)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), "an email address"),
    (re.compile(r"\b[\w-]+\.(internal|corp|lan)\b"), "an internal hostname"),
]
LEAK_ALLOW = {"noreply@anthropic.com"}
SKIP_DIRS = {".git", ".jj", "node_modules", "__pycache__"}


def check_leaks():
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            path = os.path.join(root, f)
            if path == "./tools/check.py":
                continue
            try:
                text = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                for rx, what in LEAKS:
                    m = rx.search(line)
                    if m and m.group(0) not in LEAK_ALLOW:
                        err("%s:%d: looks like %s" % (path[2:], n, what))


def check_manifests():
    import json
    for p in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", "gemini-extension.json"):
        try:
            json.load(open(p))
        except Exception as e:  # noqa: BLE001
            err("%s: %s" % (p, e))


if __name__ == "__main__":
    check_skills()
    check_evidence()
    check_manifests()
    check_leaks()
    for e in errors:
        print("FAIL " + e)
    print("%d problem(s)" % len(errors))
    sys.exit(1 if errors else 0)
