"""Render a Report as Markdown or JSON."""

import json
from dataclasses import asdict

from .checks import LEVELS, Report

LABEL = {"error": "ERROR", "warning": "WARN", "info": "INFO", "ok": "OK"}


def to_json(rep: Report, fail_on: str = "error") -> str:
    d = asdict(rep)
    d["summary"] = {lvl: rep.count(lvl) for lvl in LEVELS}
    d["exit_code"] = rep.exit_code(fail_on)
    return json.dumps(d, indent=2)


def to_markdown(rep: Report) -> str:
    out = [f"# Web manifest check: {rep.url}", ""]
    out.append("Manifest: " + (rep.manifest_url or "not found"))
    out.append(f"Result: {rep.count('error')} error(s), {rep.count('warning')} warning(s), "
               f"{rep.count('info')} info, {rep.count('ok')} ok ({rep.requests} HTTP requests)")
    out.append("")
    for lvl in LEVELS:
        items = [f for f in rep.findings if f.level == lvl]
        if not items:
            continue
        out.append(f"## {LABEL[lvl]} ({len(items)})")
        out.append("")
        for f in items:
            tail = f" <{f.url}>" if f.url and f.url not in f.message else ""
            out.append(f"- `{f.code}` {f.message}{tail}")
        out.append("")
    if rep.icons:
        out += ["## Manifest icons", "", "| src | declared | real | format | purpose | status |", "|---|---|---|---|---|---|"]
        for i in rep.icons:
            real = "x".join(map(str, i["actual"])) if i["actual"] else "-"
            out.append(f"| {i['src']} | {i['declared_sizes'] or '-'} | {real} | {i['format'] or '-'} | {i['purpose']} | {i['status']} |")
        out.append("")
    if rep.browser is not None:
        b = rep.browser
        out += ["## Browser (headless Chromium)", "",
                f"- service workers registered: {len(b['registrations'])}",
                f"- controlling this page: {'yes' if b['controller'] else 'no'}",
                f"- secure context: {'yes' if b['secure'] else 'no'}",
                f"- beforeinstallprompt seen: {'yes' if b['installPromptSeen'] else 'no'}", ""]
    out.append("## Missing icons")
    out.append("")
    out.append(", ".join(f"`{m}`" for m in rep.missing) if rep.missing else "None.")
    out.append("")
    return "\n".join(out)
