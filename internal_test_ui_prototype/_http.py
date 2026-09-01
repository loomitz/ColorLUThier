# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Loopback HTTP surface and full server-side render for the prototype."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from colorluthier_engine import JobState

from ._application import PrototypeApplication
from ._synthetic import synthetic_color_context_declaration


_HOST = "127.0.0.1"
_MAX_FORM_BYTES = 64 * 1024
_TERMINAL_JOB_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
    JobState.STALE,
}


def create_server(
    application: PrototypeApplication,
    *,
    port: int = 0,
) -> HTTPServer:
    """Create an activated loopback-only server on an explicit or ephemeral port."""

    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 through 65535")

    class PrototypeRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            self._send_render()

        def do_POST(self) -> None:
            if self.path != "/action":
                self.send_error(404)
                return
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                self.send_error(415)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if not 0 <= content_length <= _MAX_FORM_BYTES:
                self.send_error(413)
                return
            try:
                encoded_form = self.rfile.read(content_length).decode("utf-8")
            except UnicodeError:
                self.send_error(400)
                return
            try:
                parsed = parse_qs(
                    encoded_form,
                    keep_blank_values=True,
                    strict_parsing=False,
                    max_num_fields=64,
                )
            except ValueError:
                self.send_error(400)
                return
            fields = {name: values[-1] for name, values in parsed.items()}
            action = fields.pop("action", "")
            application.dispatch_action(action, fields)
            self._send_render()

        def _send_render(self) -> None:
            payload = render_page(application)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return HTTPServer((_HOST, port), PrototypeRequestHandler)


def server_url(server: HTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/"


def render_page(application: PrototypeApplication) -> bytes:
    """Render one complete frame from exactly one accepted adapter state."""

    state = application.current
    snapshot = state.snapshot
    pending_job_ids = application.pending_job_ids
    notice = application.notice
    contexts = snapshot.color_contexts
    transformation = snapshot.transformation

    reference_html = "<p class='empty'>No Reference image loaded.</p>"
    if snapshot.reference is not None:
        reference = snapshot.reference
        reference_html = f"""
        <dl data-testid="reference-metadata">
          <dt>Revision</dt><dd>{reference.revision.value}</dd>
          <dt>Encoded SHA-256</dt><dd><code>{escape(reference.encoded_sha256)}</code></dd>
          <dt>Dimensions</dt><dd>{reference.width} × {reference.height}</dd>
          <dt>Format</dt><dd>{escape(reference.image_format.value)}</dd>
          <dt>Source status</dt><dd>{escape(reference.source_color_context_status)}</dd>
          <dt>Interpretation</dt><dd>{escape(reference.interpretation_status)}</dd>
          <dt>Source context</dt><dd><code>{escape(repr(reference.source_color_context))}</code></dd>
        </dl>
        """

    transformation_html = "<p class='empty'>No Color transformation loaded.</p>"
    if transformation is not None:
        transformation_html = f"""
        <dl data-testid="transformation-metadata">
          <dt>Revision</dt><dd>{transformation.revision.value}</dd>
          <dt>Portable Cube SHA-256</dt><dd><code>{escape(transformation.portable_cube_sha256)}</code></dd>
          <dt>Lattice</dt><dd>{transformation.lattice_size}</dd>
          <dt>Interpolation</dt><dd>{escape(transformation.interpolation.value)}</dd>
          <dt>Bypass</dt><dd>{str(transformation.bypass).lower()}</dd>
          <dt>Mix</dt><dd>{transformation.mix!r}</dd>
        </dl>
        """

    diagnostics_html = "<p class='empty'>No command diagnostic.</p>"
    if state.diagnostic is not None:
        diagnostic = state.diagnostic
        bounded_message = diagnostic.message[:240]
        diagnostics_html = f"""
        <dl data-testid="command-diagnostic">
          <dt>Code</dt><dd><code>{escape(diagnostic.code)}</code></dd>
          <dt>Message</dt><dd>{escape(bounded_message)}</dd>
          <dt>Context</dt><dd><code>{escape(repr(diagnostic.context))}</code></dd>
        </dl>
        """

    notice_html = ""
    if notice is not None:
        notice_html = f"""
        <aside class="notice" role="status" data-testid="ui-notice">
          <strong>{escape(notice.code)}</strong> — {escape(notice.message[:240])}
        </aside>
        """

    jobs_html = "<p class='empty'>No jobs submitted.</p>"
    if snapshot.jobs:
        job_rows = []
        for job in snapshot.jobs:
            pending = job.job_id.value in pending_job_ids
            controls = ""
            if pending:
                controls += _job_form("step-job", "Step", job.job_id.value)
                controls += _job_form("run-job", "Run to terminal", job.job_id.value)
            if job.state not in _TERMINAL_JOB_STATES:
                controls += _job_form("cancel-job", "Cancel", job.job_id.value)
            job_diagnostic = ""
            if job.diagnostic is not None:
                job_diagnostic = (
                    f"<code>{escape(job.diagnostic.code)}</code><br>"
                    f"{escape(job.diagnostic.message[:160])}<br>"
                    f"<code>{escape(repr(job.diagnostic.context))}</code>"
                )
            job_rows.append(
                f"""
                <tr data-testid="job-{job.job_id.value}"
                    data-job-state="{escape(job.state.value)}"
                    data-progress-completed="{job.progress.completed_units}"
                    data-progress-total="{job.progress.total_units}">
                  <td>{job.job_id.value}</td>
                  <td>{escape(job.purpose.value)}</td>
                  <td>{escape(job.state.value)}</td>
                  <td><progress value="{job.progress.completed_units}"
                                max="{job.progress.total_units}"></progress>
                      {job.progress.completed_units}/{job.progress.total_units}</td>
                  <td>{job_diagnostic}</td>
                  <td class="actions">{controls}</td>
                </tr>
                """
            )
        jobs_html = f"""
        <table data-testid="jobs">
          <thead><tr><th>ID</th><th>Purpose</th><th>State</th><th>Progress</th><th>Diagnostic</th><th>Actions</th></tr></thead>
          <tbody>{''.join(job_rows)}</tbody>
        </table>
        """

    surfaces = []
    if snapshot.preview is not None:
        surfaces.append(_surface_card("Preview original", snapshot.preview.original))
        surfaces.append(_surface_card("Preview processed", snapshot.preview.processed))
    if snapshot.full_resolution is not None:
        surfaces.append(
            _surface_card(
                "Full-resolution processed",
                snapshot.full_resolution.processed,
            )
        )
    surfaces_html = (
        "<p class='empty'>No published diagnostic surfaces.</p>"
        if not surfaces
        else "".join(surfaces)
    )

    canonical_html = "<p class='empty'>No canonical artifact published.</p>"
    if state.canonical_artifact is not None:
        artifact = state.canonical_artifact
        canonical_html = f"""
        <dl data-testid="canonical-artifact">
          <dt>Artifact ID</dt><dd>{artifact.artifact_id.value}</dd>
          <dt>Job ID</dt><dd>{artifact.job_id.value}</dd>
          <dt>Basis</dt><dd><code>{escape(repr(artifact.basis))}</code></dd>
          <dt>SHA-256</dt><dd><code>{escape(artifact.sha256)}</code></dd>
          <dt>Byte count</dt><dd>{artifact.byte_count}</dd>
          <dt>Canonical bytes</dt><dd><pre>{escape(repr(artifact.encoded))}</pre></dd>
        </dl>
        """

    selected_interpolation = (
        "trilinear" if transformation is None else transformation.interpolation.value
    )
    selected_mix = 1.0 if transformation is None else transformation.mix
    selected_bypass = False if transformation is None else transformation.bypass
    trilinear_selected = " selected" if selected_interpolation == "trilinear" else ""
    tetrahedral_selected = (
        " selected" if selected_interpolation == "tetrahedral" else ""
    )
    bypass_checked = " checked" if selected_bypass else ""
    synthetic_declaration = synthetic_color_context_declaration()

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Disposable Internal Test UI</title>
  <style>
    :root {{ color-scheme: dark; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    body {{ margin: 0; background: #111318; color: #edf0f5; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 14px 20px; background: #6b1f1f; border-bottom: 2px solid #ffb36a; }}
    header strong {{ letter-spacing: .08em; }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; }}
    section {{ background: #1a1e26; border: 1px solid #394150; border-radius: 8px; padding: 14px; overflow: auto; }}
    h1, h2, h3 {{ margin-top: 0; }}
    h1 {{ font-size: 18px; margin-bottom: 4px; }}
    h2 {{ font-size: 16px; color: #9ecbff; }}
    h3 {{ font-size: 14px; color: #ffd299; }}
    dl {{ display: grid; grid-template-columns: minmax(120px, auto) 1fr; gap: 6px 12px; margin: 0; }}
    dt {{ color: #aab3c2; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
    code, pre {{ color: #b8f0ca; white-space: pre-wrap; overflow-wrap: anywhere; }}
    form {{ display: inline-flex; flex-wrap: wrap; align-items: end; gap: 7px; margin: 4px 4px 4px 0; }}
    label {{ display: inline-grid; gap: 3px; color: #c5ccd8; }}
    input, select, button {{ font: inherit; padding: 6px 8px; border-radius: 5px; border: 1px solid #576174; background: #262c37; color: #fff; }}
    input[type=text] {{ min-width: 260px; }} button {{ cursor: pointer; border-color: #7ea7d8; }}
    button:hover {{ background: #354157; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #394150; padding: 7px; vertical-align: top; }}
    .actions form {{ display: inline-flex; margin: 1px; }}
    .notice {{ margin: 0 0 14px; padding: 10px; border: 1px solid #e4bd63; background: #40351d; }}
    .capability {{ border-color: #d96c6c; }} .blocked {{ color: #ff9999; font-weight: 700; }}
    .surface {{ border-left: 4px solid #b589e8; margin: 10px 0; padding-left: 10px; }}
    .label {{ color: #e7b9ff; font-weight: 700; }} .empty {{ color: #7f8999; }}
    progress {{ width: 110px; }}
  </style>
</head>
<body>
  <header role="banner" data-testid="prototype-banner">
    <h1>DISPOSABLE INTERNAL TEST UI — NOT PRODUCT UI</h1>
    <strong>Question:</strong> Can one single-process browser surface make the adapter operable and visible without duplicating domain state?
  </header>
  <main>
    {notice_html}
    <section aria-labelledby="controls-heading">
      <h2 id="controls-heading">Actions</h2>
      {_simple_form("load-synthetic", "Load synthetic Reference + Cube")}
      {_simple_form("open-synthetic-reference", "Open synthetic PPM")}
      {_simple_form("load-synthetic-cube", "Load synthetic Cube")}
      {_simple_form("request-preview", "Request preview")}
      {_simple_form("request-full", "Request full-resolution")}
      {_simple_form("inspect-canonical", "Inspect canonical artifact")}
      {_simple_form("stale-demo", "Run newest-before-oldest stale demo")}
      {_simple_form("malformed-reference", "Submit malformed Reference")}
      <hr>
      <form method="post" action="/action" data-testid="reference-path-form">
        <input type="hidden" name="action" value="open-reference-path">
        <label>Reference path <input type="text" name="reference-path" autocomplete="off"></label>
        <label>Format <select name="image-format">
          <option value="ppm-p6-rgb8">PPM P6 RGB8</option>
          <option value="png-rgb8">PNG RGB/RGBA decoded to RGB8</option>
        </select></label>
        <button type="submit">Open path read-only</button>
      </form>
      <form method="post" action="/action" data-testid="cube-path-form">
        <input type="hidden" name="action" value="load-cube-path">
        <label>Cube path <input type="text" name="cube-path" autocomplete="off"></label>
        <label>Interpolation <select name="interpolation">
          <option value="trilinear"{trilinear_selected}>Trilinear</option>
          <option value="tetrahedral"{tetrahedral_selected}>Tetrahedral</option>
        </select></label>
        <label><input type="checkbox" name="bypass"{bypass_checked}> Bypass</label>
        <label>Mix <input type="text" name="mix" value="{selected_mix!r}"></label>
        <button type="submit">Load path read-only</button>
      </form>
      <form method="post" action="/action" data-testid="configure-form">
        <input type="hidden" name="action" value="configure-transformation">
        <label>Interpolation <select name="interpolation">
          <option value="trilinear"{trilinear_selected}>Trilinear</option>
          <option value="tetrahedral"{tetrahedral_selected}>Tetrahedral</option>
        </select></label>
        <label><input type="checkbox" name="bypass"{bypass_checked}> Bypass</label>
        <label>Mix <input type="text" name="mix" value="{selected_mix!r}"></label>
        <button type="submit">Configure transformation</button>
      </form>
      <form method="post" action="/action" data-testid="declare-contexts-form">
        <input type="hidden" name="action" value="declare-contexts">
        <input type="hidden" name="expected-interpretation" value="{contexts.interpretation_revision.value}">
        <input type="hidden" name="expected-viewing" value="{contexts.viewing_revision.value}">
        <input type="hidden" name="expected-export" value="{contexts.export_revision.value}">
        <button type="submit">Declare complete synthetic ICC + Export contexts</button>
      </form>
      <details><summary>Exact synthetic declaration</summary><pre data-testid="synthetic-declaration">{escape(repr(synthetic_declaration))}</pre></details>
    </section>

    <div class="grid">
      <section aria-labelledby="snapshot-heading">
        <h2 id="snapshot-heading">One accepted adapter snapshot</h2>
        <dl data-testid="snapshot-revisions">
          <dt>Snapshot revision</dt><dd>{snapshot.snapshot_revision.value}</dd>
          <dt>Document revision</dt><dd>{snapshot.document_revision.value}</dd>
          <dt>Command status</dt><dd>{escape("none" if state.command_status is None else state.command_status.value)}</dd>
          <dt>Submitted job</dt><dd>{"none" if state.submitted_job_id is None else state.submitted_job_id.value}</dd>
          <dt>Watermark</dt><dd>{state.watermark.value}</dd>
        </dl>
      </section>
      <section aria-labelledby="diagnostic-heading">
        <h2 id="diagnostic-heading">Diagnostics</h2>{diagnostics_html}
      </section>
      <section aria-labelledby="reference-heading">
        <h2 id="reference-heading">Reference image</h2>{reference_html}
      </section>
      <section aria-labelledby="transformation-heading">
        <h2 id="transformation-heading">Color transformation</h2>{transformation_html}
      </section>
      <section aria-labelledby="contexts-heading">
        <h2 id="contexts-heading">Explicit Color contexts</h2>
        <dl data-testid="color-contexts">
          <dt>Interpretation revision</dt><dd>{contexts.interpretation_revision.value}</dd>
          <dt>Viewing revision</dt><dd>{contexts.viewing_revision.value}</dd>
          <dt>Export revision</dt><dd>{contexts.export_revision.value}</dd>
          <dt>Declaration</dt><dd><code>{escape(repr(contexts.declaration))}</code></dd>
          <dt>Export independent</dt><dd><code>{escape(repr(contexts.export_context))}</code></dd>
        </dl>
      </section>
      <section class="capability" aria-labelledby="export-heading">
        <h2 id="export-heading">Ordinary export capability</h2>
        <output class="blocked" data-testid="ordinary-export-status">{escape(state.ordinary_export_status)}</output>
      </section>
    </div>

    <section aria-labelledby="jobs-heading"><h2 id="jobs-heading">Jobs and deterministic progress</h2>{jobs_html}</section>
    <section aria-labelledby="surfaces-heading"><h2 id="surfaces-heading">Original and processed diagnostic presentation</h2>{surfaces_html}</section>
    <section aria-labelledby="canonical-heading"><h2 id="canonical-heading">Canonical Portable Cube inspection</h2>{canonical_html}</section>
  </main>
</body>
</html>
"""
    return html.encode("utf-8")


def _simple_form(action: str, label: str) -> str:
    return f"""
    <form method="post" action="/action">
      <input type="hidden" name="action" value="{escape(action)}">
      <button type="submit">{escape(label)}</button>
    </form>
    """


def _job_form(action: str, label: str, job_id: int) -> str:
    return f"""
    <form method="post" action="/action">
      <input type="hidden" name="action" value="{escape(action)}">
      <input type="hidden" name="job-id" value="{job_id}">
      <button type="submit">{escape(label)}</button>
    </form>
    """


def _surface_card(label: str, surface: object) -> str:
    pixels = surface.pixels
    prefix = pixels[:48].hex()
    return f"""
    <article class="surface" data-testid="surface-{surface.surface_id.value}">
      <h3>{escape(label)}</h3>
      <p class="label">diagnostic visualization · {escape(surface.viewing_status)}</p>
      <dl>
        <dt>Surface ID</dt><dd>{surface.surface_id.value}</dd>
        <dt>Purpose</dt><dd>{escape(surface.purpose.value)}</dd>
        <dt>Basis</dt><dd><code>{escape(repr(surface.basis))}</code></dd>
        <dt>Dimensions</dt><dd>{surface.width} × {surface.height}</dd>
        <dt>Row stride</dt><dd>{surface.row_stride}</dd>
        <dt>Encoding</dt><dd>{escape(surface.encoding.value)}</dd>
        <dt>Pixel byte count</dt><dd>{len(pixels)}</dd>
        <dt>Bounded byte prefix</dt><dd><code>{prefix}</code></dd>
      </dl>
    </article>
    """
