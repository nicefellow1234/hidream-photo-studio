from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, FormData, web


APP_DIR = Path(os.environ.get("HIDREAM_STATE_DIR", str(Path(__file__).resolve().parent))).resolve()
COMFY_URL = os.environ.get("HIDREAM_COMFY_URL", "http://127.0.0.1:8188")
OUTPUT_DIR = Path(os.environ.get("HIDREAM_OUTPUT_DIR", str(APP_DIR / "output"))).resolve()
HISTORY_PATH = APP_DIR / "history.json"
MODEL_NAME = os.environ.get("HIDREAM_MODEL_NAME", "HiDream-O1-Image-Dev-FP8")
RESIDENT_TORCH_VRAM_BYTES = 7 * 1024 * 1024 * 1024
MAX_REFERENCE_IMAGES = int(os.environ.get("HIDREAM_MAX_REFERENCE_IMAGES", "12"))
MAX_HISTORY_JOBS = int(os.environ.get("HIDREAM_MAX_HISTORY_JOBS", "80"))
APP_HOST = os.environ.get("HIDREAM_APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("HIDREAM_APP_PORT", "7860"))

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOADED = False
ENGINE: dict[str, Any] = {
    "comfy": False,
    "status": "starting",
    "message": "Starting image engine...",
    "prompt_id": None,
    "error": None,
    "ready_at": None,
}
WARMUP_TASK: asyncio.Task | None = None

ASPECTS = {
    "square": {"label": "Square", "width": 2048, "height": 2048},
    "landscape": {"label": "Landscape", "width": 2560, "height": 1440},
    "portrait": {"label": "Portrait", "width": 1440, "height": 2560},
    "wide": {"label": "Wide", "width": 3104, "height": 1312},
}


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HiDream Photo Studio</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #181713;
      --muted: #6c6a61;
	      --line: #dedbd0;
	      --panel: #ffffff;
	      --preview-bg: #e9e5da;
	      --accent: #126c62;
      --accent-2: #d64c2f;
      --soft: #ebf3ee;
      --shadow: 0 18px 50px rgba(27, 25, 18, 0.10);
    }
    * { box-sizing: border-box; }
	    body {
	      margin: 0;
		      height: 100vh;
	      overflow: hidden;
	      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
	      background: var(--bg);
	      color: var(--ink);
	    }
	    main {
	      display: grid;
	      grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
	      gap: 14px;
		      height: 100vh;
	      min-height: 0;
	      padding: 12px;
	      overflow: hidden;
	    }
	    .controls {
	      align-self: stretch;
		      height: calc(100vh - 24px);
	      min-height: 0;
	      display: flex;
	      flex-direction: column;
	      background: var(--panel);
	      border: 1px solid var(--line);
	      box-shadow: var(--shadow);
	      padding: 14px;
	      border-radius: 8px;
	      overflow: hidden;
	    }
	    h1 {
	      margin: 0 0 8px;
	      font-size: 20px;
      line-height: 1.08;
      letter-spacing: 0;
    }
	    label {
	      display: block;
	      margin: 8px 0 4px;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
    }
    textarea, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
	    textarea {
	      min-height: 64px;
	      padding: 8px 9px;
	      resize: none;
	      line-height: 1.45;
	      overflow: auto;
	    }
	    #prompt {
	      flex: 0 0 auto;
	      height: clamp(120px, 24dvh, 190px);
	      min-height: 0;
	      max-height: none;
	    }
    #negative-prompt {
      min-height: 58px;
    }
    details.advanced {
      margin-top: 8px;
    }
    details.advanced summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      list-style: none;
      user-select: none;
    }
    details.advanced summary::-webkit-details-marker {
      display: none;
    }
    details.advanced summary::before {
      content: "+";
      display: inline-block;
      width: 16px;
      color: var(--accent);
      font-weight: 800;
    }
    details.advanced[open] summary::before {
      content: "-";
    }
    details.advanced label {
      margin-top: 8px;
    }
    input { padding: 8px 10px; }
    input[type="file"] {
      display: none;
    }
	    .dropzone {
      border: 1px dashed #b9b4a6;
      border-radius: 6px;
      background: #fbfaf6;
	      padding: 8px 9px;
      color: var(--muted);
      cursor: pointer;
      line-height: 1.25;
      font-size: 12px;
    }
    .dropzone strong {
      display: block;
      color: var(--ink);
      margin-bottom: 2px;
    }
	    .refs {
	      display: grid;
	      grid-template-columns: repeat(4, 1fr);
	      gap: 6px;
	      margin-top: 6px;
	      max-height: 58px;
	      overflow: hidden;
    }
    .refs img {
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
    }
    .inline-check {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
      text-transform: none;
      font-weight: 600;
    }
    .inline-check input {
      width: auto;
    }
	    .segmented {
	      display: grid;
	      grid-template-columns: repeat(2, 1fr);
	      gap: 6px;
	    }
	    .segmented button {
	      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      cursor: pointer;
      font-weight: 650;
      font-size: 13px;
      line-height: 1.15;
    }
    .segmented button span {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
    }
    .segmented button.active {
      border-color: var(--accent);
      background: var(--soft);
      color: var(--accent);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
	    .primary {
	      width: 100%;
	      height: 42px;
	      margin-top: 12px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 750;
      cursor: pointer;
      flex: 0 0 auto;
    }
    .primary:disabled {
      cursor: wait;
      opacity: .62;
    }
	    .status {
	      margin-top: 8px;
      min-height: 22px;
      color: var(--muted);
      font-size: 14px;
      flex: 0 0 auto;
    }
			    .viewer {
			      min-width: 0;
			      min-height: 0;
			      display: grid;
			      grid-template-rows: auto minmax(0, 1fr);
			      gap: 10px;
			      height: calc(100vh - 24px);
			      overflow: hidden;
			    }
	    .topline {
	      display: flex;
	      align-items: center;
	      justify-content: space-between;
	      gap: 12px;
	      color: var(--muted);
	      font-size: 14px;
	    }
	    .top-actions {
	      display: flex;
	      align-items: center;
	      gap: 8px;
	      flex: 0 0 auto;
	    }
	    .download {
	      border: 1px solid var(--line);
	      border-radius: 999px;
	      padding: 6px 11px;
	      background: #fff;
	      color: var(--accent);
	      font: inherit;
	      font-size: 13px;
	      font-weight: 750;
	      text-decoration: none;
	      cursor: pointer;
	      white-space: nowrap;
	    }
	    .download.disabled {
	      color: var(--muted);
	      opacity: .5;
	      pointer-events: none;
	      cursor: default;
	    }
			    .output {
				      height: min(calc(100vh - 72px), calc((100vw - 410px) * 9 / 16));
				      width: auto;
				      max-width: 100%;
				      justify-self: center;
				      align-self: center;
				      aspect-ratio: 16 / 9;
					      max-height: calc(100vh - 72px);
				      min-height: 0;
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      background: var(--preview-bg);
		      display: flex;
		      align-items: center;
		      justify-content: center;
	      overflow: hidden;
      position: relative;
    }
    .empty {
      max-width: 420px;
      padding: 30px;
      text-align: center;
      color: var(--muted);
      line-height: 1.5;
    }
		    .output img {
			      width: 100%;
				      height: 100vh;
				      max-height: 100%;
				      margin: auto 0;
				      object-fit: contain;
		      object-position: center center;
			      display: block;
			      background: var(--preview-bg);
		    }
	    .history-modal[hidden] {
	      display: none;
	    }
	    .history-modal {
	      position: fixed;
	      inset: 0;
	      z-index: 10;
	      display: grid;
	      place-items: center;
	      padding: 22px;
	      background: rgba(24, 23, 19, .42);
	    }
	    .history-panel {
	      width: min(1040px, 92vw);
		      max-height: 84vh;
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      background: var(--panel);
	      box-shadow: var(--shadow);
	      padding: 14px;
	      overflow: hidden;
	    }
		    .history-head {
	      display: flex;
	      align-items: center;
	      justify-content: space-between;
	      margin-bottom: 8px;
	      color: var(--muted);
	      font-size: 13px;
	      font-weight: 700;
	      text-transform: uppercase;
	    }
		    .history-grid {
		      display: grid;
		      grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
		      gap: 8px;
			      max-height: calc(84vh - 58px);
		      overflow: auto;
		      padding-right: 2px;
		    }
	    .history-card {
	      min-width: 0;
	      border: 1px solid var(--line);
	      border-radius: 7px;
	      background: #fff;
	      padding: 6px;
	      cursor: pointer;
	    }
	    .history-card.active {
	      border-color: var(--accent);
	      box-shadow: 0 0 0 1px var(--accent);
	    }
	    .history-card img,
	    .history-placeholder {
	      width: 100%;
	      aspect-ratio: 4 / 3;
	      border-radius: 5px;
	      display: grid;
	      place-items: center;
	      object-fit: cover;
	      background: #edeae1;
	      color: var(--muted);
	      font-size: 12px;
	      text-align: center;
	    }
	    .history-meta {
	      margin-top: 5px;
	      overflow: hidden;
	      text-overflow: ellipsis;
	      white-space: nowrap;
	      color: var(--muted);
	      font-size: 12px;
	    }
	    .pill {
	      border: 1px solid var(--line);
	      border-radius: 999px;
      padding: 6px 10px;
      background: rgba(255,255,255,.68);
      white-space: nowrap;
    }
	    .error { color: var(--accent-2); }
		    @media (max-width: 920px) {
		      body { overflow: auto; }
		      main { grid-template-columns: 1fr; height: auto; overflow: visible; }
		      .controls, .viewer { height: auto; overflow: visible; }
		      .output { aspect-ratio: 16 / 9; }
		    }
  </style>
</head>
<body>
  <main>
    <section class="controls">
      <h1>HiDream Photo Studio</h1>
      <label for="prompt">Prompt</label>
      <textarea id="prompt">A realistic professional photo of a steaming ceramic coffee cup on a wooden table beside a window, morning sunlight, shallow depth of field, natural colors, crisp details, 50mm lens photography.</textarea>

      <details class="advanced">
        <summary>Negative prompt</summary>
        <label for="negative-prompt">Negative prompt</label>
        <textarea id="negative-prompt">low quality, blurry, distorted, text, watermark</textarea>
      </details>

      <label for="refs-input">Reference photos</label>
      <label class="dropzone" for="refs-input">
        <strong>Add reference photos</strong>
        Single photo edits it; multiple photos guide a new image.
      </label>
      <input id="refs-input" type="file" accept="image/*" multiple />
      <div class="refs" id="refs"></div>
      <label class="inline-check">
        <input id="keep-aspect" type="checkbox" />
        Keep first photo aspect
      </label>

      <label>Aspect</label>
      <div class="segmented" id="aspect">
        <button class="active" data-aspect="square">Square<span>1:1 · 2048x2048</span></button>
        <button data-aspect="landscape">Landscape<span>16:9 · 2560x1440</span></button>
        <button data-aspect="portrait">Portrait<span>9:16 · 1440x2560</span></button>
        <button data-aspect="wide">Wide<span>2.37:1 · 3104x1312</span></button>
      </div>

      <div class="row">
        <div>
          <label for="seed">Seed</label>
          <input id="seed" type="number" min="0" value="123456789" />
        </div>
        <div>
          <label for="prefix">Name</label>
          <input id="prefix" type="text" value="hidream_photo" />
        </div>
      </div>

      <button class="primary" id="generate" disabled>Generate Photo</button>
      <div class="status" id="status">Starting image engine...</div>
    </section>

	    <section class="viewer">
	      <div class="topline">
		        <span id="engine">Checking engine...</span>
		        <div class="top-actions">
		          <button class="download" id="history-toggle" type="button">Recent</button>
		          <a class="download disabled" id="download" href="#" aria-disabled="true">Download</a>
		          <span class="pill" id="model">HiDream Dev FP8</span>
		        </div>
	      </div>
		      <div class="output" id="output">
		        <div class="empty">Your generated photo will appear here.</div>
		      </div>
		    </section>
	  </main>
	  <div class="history-modal" id="history-modal" hidden>
	    <div class="history-panel" role="dialog" aria-modal="true" aria-labelledby="history-title">
	      <div class="history-head">
	        <span id="history-title">Recent Images</span>
	        <button class="download" id="history-close" type="button">Close</button>
	      </div>
	      <div class="history-grid" id="history-grid"></div>
	    </div>
	  </div>

	  <script>
    const $ = (id) => document.getElementById(id);
    let aspect = "square";
    let pollTimer = null;
	    let elapsedTimer = null;
	    let engineReady = false;
	    let generating = false;
	    let currentJobId = null;
	    let selectedJob = null;
	    let refFiles = [];

    document.querySelectorAll("#aspect button").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("#aspect button").forEach((b) => b.classList.remove("active"));
        button.classList.add("active");
        aspect = button.dataset.aspect;
      });
    });

	    $("refs-input").addEventListener("change", () => {
	      refFiles = Array.from($("refs-input").files || []).slice(0, 12);
	      renderRefs();
	    });

	    $("history-toggle").addEventListener("click", () => {
	      $("history-modal").hidden = false;
	      loadHistory();
	    });

	    $("history-close").addEventListener("click", () => {
	      $("history-modal").hidden = true;
	    });

	    $("history-modal").addEventListener("click", (event) => {
	      if (event.target === $("history-modal")) $("history-modal").hidden = true;
	    });

	    document.addEventListener("keydown", (event) => {
	      if (event.key === "Escape") $("history-modal").hidden = true;
	    });

	    function renderRefs() {
      $("refs").innerHTML = "";
      for (const file of refFiles) {
        const img = document.createElement("img");
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        $("refs").appendChild(img);
      }
    }

    async function refreshHealth() {
      try {
        const res = await fetch("/api/health");
        const data = await res.json();
        engineReady = data.status === "ready";
	        $("engine").textContent = data.message;
	        $("engine").className = data.status === "error" || data.status === "offline" ? "error" : "";
	        $("generate").disabled = !engineReady || generating;
	        if (!generating && selectedJob?.status === "done") {
	          setStatus(doneStatus(selectedJob));
	        } else if (!generating) {
	          setStatus(data.message, data.status === "error" || data.status === "offline");
	        }
      } catch {
        engineReady = false;
        $("engine").textContent = "Engine offline";
        $("engine").className = "error";
        $("generate").disabled = true;
        if (!generating) setStatus("Engine offline.", true);
      }
    }

    function setStatus(text, error = false) {
      $("status").textContent = text;
      $("status").className = error ? "status error" : "status";
    }

    function stopTimers() {
      clearInterval(pollTimer);
      clearInterval(elapsedTimer);
      pollTimer = null;
      elapsedTimer = null;
    }

	    function startElapsedTimer(startedAt) {
	      clearInterval(elapsedTimer);
	      const update = () => {
	        const elapsed = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
	        setStatus(`Generating... ${elapsed}s elapsed`);
	      };
	      update();
	      elapsedTimer = setInterval(() => {
	        update();
	      }, 1000);
	    }

	    function imageUrl(job, bustCache = false) {
	      if (!job.image_url) return "";
	      return `${job.image_url}${job.image_url.includes("?") ? "&" : "?"}t=${bustCache ? Date.now() : job.created || ""}`;
	    }

	    function formatDuration(seconds) {
	      const value = Math.max(0, Math.round(Number(seconds) || 0));
	      const minutes = Math.floor(value / 60);
	      const rest = value % 60;
	      if (!minutes) return `${rest}s`;
	      return `${minutes}m ${String(rest).padStart(2, "0")}s`;
	    }

	    function jobDuration(job, fallback = null) {
	      const value = Number(job?.duration_seconds);
	      if (Number.isFinite(value) && value >= 0) return Math.round(value);
	      return fallback;
	    }

	    function doneStatus(job, fallback = null) {
	      const duration = jobDuration(job, fallback);
	      const filename = job?.filename || "photo";
	      if (duration === null || duration === undefined) return `Saved as ${filename}.`;
	      return `Generated in ${formatDuration(duration)}. Saved as ${filename}.`;
	    }

	    function setDownload(job) {
	      const download = $("download");
	      if (!job || !job.image_url || job.status !== "done") {
	        download.href = "#";
	        download.removeAttribute("download");
	        download.setAttribute("aria-disabled", "true");
	        download.classList.add("disabled");
	        return;
	      }
	      download.href = imageUrl(job);
	      download.download = job.filename || "hidream_photo.png";
	      download.removeAttribute("aria-disabled");
	      download.classList.remove("disabled");
	    }

	    function showImage(job, bustCache = false) {
	      if (!job || !job.image_url) return;
	      currentJobId = job.job_id;
	      selectedJob = job;
	      $("output").innerHTML = "";
	      const img = document.createElement("img");
	      img.alt = "Generated HiDream photo";
	      img.src = imageUrl(job, bustCache);
	      $("output").appendChild(img);
	      setDownload(job);
	      document.querySelectorAll(".history-card").forEach((card) => {
	        card.classList.toggle("active", card.dataset.jobId === currentJobId);
	      });
	    }

	    function beginJob(job) {
	      stopTimers();
	      currentJobId = job.job_id;
	      generating = true;
	      selectedJob = null;
	      $("generate").disabled = true;
	      $("output").innerHTML = `<div class="empty">Generating...</div>`;
	      setDownload(null);
	      const startedAt = Number(job.created || 0) > 0 ? Number(job.created) * 1000 : Date.now();
	      startElapsedTimer(startedAt);
	      pollTimer = setInterval(() => poll(job.job_id, startedAt), 4000);
	      poll(job.job_id, startedAt);
	    }

	    async function poll(jobId, startedAt) {
	      let data;
	      try {
	        const res = await fetch(`/api/jobs/${jobId}`);
	        data = await res.json();
	        if (!res.ok) throw new Error(data.error || "Could not check job status.");
	      } catch (err) {
	        setStatus(err.message || String(err), true);
	        return;
	      }

	      const elapsed = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
	      if (data.status === "done") {
	        stopTimers();
	        generating = false;
	        currentJobId = data.job_id;
	        $("generate").disabled = false;
	        showImage(data, true);
	        setStatus(doneStatus(data, elapsed));
	        loadHistory();
	      } else if (data.status === "error") {
	        stopTimers();
	        generating = false;
	        currentJobId = data.job_id;
	        $("generate").disabled = false;
	        setStatus(data.error || "Generation failed.", true);
	        loadHistory();
	      }
	    }

	    function renderHistory(jobs) {
	      const grid = $("history-grid");
	      grid.innerHTML = "";
	      if (!jobs.length) {
	        const empty = document.createElement("div");
	        empty.className = "history-placeholder";
	        empty.textContent = "No images yet";
	        grid.appendChild(empty);
	        return;
	      }

	      for (const job of jobs) {
	        const card = document.createElement("button");
	        card.type = "button";
	        card.className = "history-card";
	        card.dataset.jobId = job.job_id;
	        card.classList.toggle("active", job.job_id === currentJobId);

	        if (job.image_url) {
	          const img = document.createElement("img");
	          img.alt = job.filename || "Generated photo";
	          img.src = imageUrl(job);
	          card.appendChild(img);
	        } else {
	          const placeholder = document.createElement("div");
	          placeholder.className = "history-placeholder";
	          placeholder.textContent = job.status === "error" ? "Failed" : "Generating";
	          card.appendChild(placeholder);
	        }

	        const meta = document.createElement("div");
	        meta.className = "history-meta";
	        const duration = jobDuration(job);
	        const label = job.filename || job.prompt || job.status;
	        meta.textContent = duration === null ? label : `${formatDuration(duration)} · ${label}`;
	        card.appendChild(meta);

		        card.addEventListener("click", () => {
			          if (job.status === "done" && job.image_url) {
			            showImage(job);
			            setStatus(doneStatus(job));
	          } else if (job.status === "queued" || job.status === "running") {
	            beginJob(job);
	          } else if (job.error) {
	            setStatus(job.error, true);
	          }
	        });
	        grid.appendChild(card);
	      }
	    }

	    async function loadHistory(options = {}) {
	      try {
	        const res = await fetch("/api/jobs");
	        const data = await res.json();
	        if (!res.ok) throw new Error(data.error || "Could not load history.");
	        const jobs = data.jobs || [];
	        renderHistory(jobs);

	        if (options.restore && !generating) {
	          const running = jobs.find((job) => job.status === "queued" || job.status === "running");
	          if (running) {
	            beginJob(running);
	            return;
	          }
	          const latestDone = jobs.find((job) => job.status === "done" && job.image_url);
	          if (latestDone) showImage(latestDone);
	        }
	      } catch {
	        renderHistory([]);
	      }
	    }

    $("generate").addEventListener("click", async () => {
      if (!engineReady) {
        setStatus("The model is still warming up. Generation will unlock automatically.", true);
        return;
      }
      stopTimers();
      generating = true;
      $("generate").disabled = true;
      $("output").innerHTML = `<div class="empty">Generating...</div>`;
      setStatus("Submitting prompt...");

      try {
        const form = new FormData();
        form.append("prompt", $("prompt").value);
        form.append("negative_prompt", $("negative-prompt").value);
        form.append("aspect", aspect);
        form.append("seed", String(Number($("seed").value || 0)));
        form.append("filename_prefix", $("prefix").value || "hidream_photo");
        form.append("keep_aspect", $("keep-aspect").checked ? "true" : "false");
        for (const file of refFiles) form.append("reference_images", file, file.name);

        const res = await fetch("/api/generate", { method: "POST", body: form });
	        const data = await res.json();
	        if (!res.ok) throw new Error(data.error || "Could not submit prompt.");
	        beginJob({ job_id: data.job_id, created: Date.now() / 1000 });
	        loadHistory();
	      } catch (err) {
	        stopTimers();
	        generating = false;
        $("generate").disabled = false;
        setStatus(err.message || String(err), true);
      }
    });

	    refreshHealth();
	    loadHistory({ restore: true });
	    setInterval(refreshHealth, 10000);
	    setInterval(() => loadHistory(), 15000);
	  </script>
</body>
</html>
"""


def build_prompt(
    prompt: str,
    negative_prompt: str,
    aspect: str,
    seed: int,
    filename_prefix: str,
    reference_images: list[dict[str, str]] | None = None,
    keep_aspect: bool = False,
) -> dict[str, Any]:
    dimensions = ASPECTS.get(aspect, ASPECTS["square"])
    clean_prefix = "".join(ch for ch in filename_prefix if ch.isalnum() or ch in "-_")[:64] or "hidream_photo"
    reference_images = (reference_images or [])[:MAX_REFERENCE_IMAGES]
    workflow = {
        "2": {
            "class_type": "HiDreamO1ModelLoader",
            "inputs": {
                "model_name": MODEL_NAME,
                "precision": "auto",
                "attention": "auto",
                "download_if_missing": False,
            },
        },
        "9": {
            "class_type": "HiDreamO1Conditioning",
            "inputs": {
                "prompt": prompt.strip(),
                "negative_prompt": negative_prompt.strip(),
            },
        },
        "8": {
            "class_type": "HiDreamO1Sampler",
            "inputs": {
                "model": ["2", 0],
                "conditioning": ["9", 0],
                "model_type": "auto",
                "width": dimensions["width"],
                "height": dimensions["height"],
                "steps": 0,
                "seed": seed,
                "guidance_scale": 5.0,
                "shift": -1.0,
                "noise_scale_start": 7.5,
                "noise_scale_end": 7.5,
                "noise_clip_std": 2.5,
                "preview_every": 0,
                "keep_image1_aspect": bool(keep_aspect and len(reference_images) == 1),
                "force_offload": False,
                "image": "0",
            },
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": clean_prefix,
            },
        },
    }

    if reference_images:
        workflow["8"]["inputs"]["image"] = str(len(reference_images))
        for index, image_info in enumerate(reference_images, start=1):
            node_id = str(20 + index)
            image_name = image_info["name"]
            if image_info.get("subfolder"):
                image_name = f"{image_info['subfolder']}/{image_name}"
            workflow[node_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": image_name},
            }
            workflow["8"]["inputs"][f"image.image_{index}"] = [node_id, 0]

    return workflow


def build_warmup_prompt() -> dict[str, Any]:
    return {
        "2": {
            "class_type": "HiDreamO1ModelLoader",
            "inputs": {
                "model_name": MODEL_NAME,
                "precision": "auto",
                "attention": "auto",
                "download_if_missing": False,
            },
        },
        "99": {
            "class_type": "SimpleHiDreamWarmup",
            "inputs": {
                "model": ["2", 0],
            },
        },
    }


async def comfy_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    async with ClientSession() as session:
        if method == "GET":
            async with session.get(f"{COMFY_URL}{path}", timeout=10) as response:
                response.raise_for_status()
                return await response.json()
        async with session.post(f"{COMFY_URL}{path}", json=payload, timeout=30) as response:
            response.raise_for_status()
            return await response.json()


async def upload_reference_images(request: web.Request, job_id: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    reader = await request.multipart()
    fields: dict[str, str] = {}
    images: list[dict[str, str]] = []

    async with ClientSession() as session:
        async for part in reader:
            if part.name == "reference_images":
                if len(images) >= MAX_REFERENCE_IMAGES:
                    continue
                filename = Path(part.filename or f"reference-{len(images) + 1}.png").name
                content_type = part.headers.get("Content-Type", "application/octet-stream")
                data = await part.read(decode=False)
                form = FormData()
                form.add_field(
                    "image",
                    data,
                    filename=f"{job_id}-{len(images) + 1}-{filename}",
                    content_type=content_type,
                )
                form.add_field("overwrite", "true")
                form.add_field("type", "input")
                async with session.post(f"{COMFY_URL}/upload/image", data=form, timeout=120) as response:
                    response.raise_for_status()
                    uploaded = await response.json()
                images.append({
                    "name": uploaded.get("name", ""),
                    "subfolder": uploaded.get("subfolder", ""),
                    "type": uploaded.get("type", "input"),
                })
            else:
                value = await part.text()
                fields[part.name or ""] = value

    return fields, images


async def parse_generate_request(request: web.Request, job_id: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    if request.content_type.startswith("multipart/"):
        return await upload_reference_images(request, job_id)
    data = await request.json()
    return {key: str(value) for key, value in data.items()}, []


def model_is_resident(system_stats: dict[str, Any]) -> bool:
    for device in system_stats.get("devices", []):
        if device.get("type") != "cuda":
            continue
        torch_vram_total = int(device.get("torch_vram_total") or 0)
        if torch_vram_total >= RESIDENT_TORCH_VRAM_BYTES:
            return True
    return False


def mark_ready(message: str = "Engine ready. Model is warm.") -> None:
    ENGINE.update({
        "comfy": True,
        "status": "ready",
        "message": message,
        "ready_at": time.time(),
        "error": None,
    })


def output_job_id(path: Path) -> str:
    return "file-" + uuid.uuid5(uuid.NAMESPACE_URL, str(path)).hex


def job_created(job: dict[str, Any]) -> float:
    try:
        return float(job.get("created") or 0)
    except (TypeError, ValueError):
        return 0.0


def discover_output_jobs() -> None:
    if not OUTPUT_DIR.is_dir():
        return

    known_files = {
        (str(job.get("subfolder") or ""), str(job.get("filename") or ""))
        for job in JOBS.values()
        if job.get("filename")
    }
    image_paths = [
        path
        for path in OUTPUT_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    for path in sorted(image_paths, key=lambda item: item.stat().st_mtime, reverse=True)[:MAX_HISTORY_JOBS]:
        relative = path.relative_to(OUTPUT_DIR)
        filename = relative.name
        subfolder = "" if relative.parent == Path(".") else str(relative.parent)
        if (subfolder, filename) in known_files:
            continue
        job_id = output_job_id(path)
        JOBS[job_id] = {
            "status": "done",
            "prompt_id": None,
            "created": path.stat().st_mtime,
            "error": None,
            "filename": filename,
            "subfolder": subfolder,
            "prompt": "",
            "negative_prompt": "",
            "aspect": "",
            "seed": None,
            "filename_prefix": path.stem,
            "reference_count": 0,
            "completed_at": path.stat().st_mtime,
            "duration_seconds": None,
            "source": "output",
        }


def trim_jobs() -> None:
    sorted_items = sorted(JOBS.items(), key=lambda item: job_created(item[1]), reverse=True)
    keep_ids = {
        job_id
        for job_id, job in sorted_items[:MAX_HISTORY_JOBS]
        if job.get("status") in {"done", "error"}
    }
    keep_ids.update(
        job_id
        for job_id, job in sorted_items
        if job.get("status") not in {"done", "error"}
    )
    for job_id in list(JOBS):
        if job_id not in keep_ids:
            JOBS.pop(job_id, None)


def save_jobs() -> None:
    trim_jobs()
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = HISTORY_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps({"jobs": JOBS}, indent=2), encoding="utf-8")
    tmp_path.replace(HISTORY_PATH)


def load_jobs() -> None:
    global JOBS_LOADED
    if JOBS_LOADED:
        return
    JOBS_LOADED = True

    if HISTORY_PATH.is_file():
        try:
            raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            stored_jobs = raw.get("jobs", raw)
            if isinstance(stored_jobs, dict):
                for job_id, job in stored_jobs.items():
                    if isinstance(job, dict):
                        JOBS[str(job_id)] = job
            elif isinstance(stored_jobs, list):
                for job in stored_jobs:
                    if isinstance(job, dict) and job.get("job_id"):
                        job_id = str(job.pop("job_id"))
                        JOBS[job_id] = job
        except Exception:
            pass

    discover_output_jobs()
    save_jobs()


async def index(_request: web.Request) -> web.Response:
    return web.Response(
        text=INDEX_HTML,
        content_type="text/html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


async def health(_request: web.Request) -> web.Response:
    try:
        stats = await comfy_json("GET", "/system_stats")
        ENGINE["comfy"] = True
        if ENGINE["status"] != "ready" and model_is_resident(stats):
            mark_ready("Engine ready. Model is already loaded.")
    except Exception:
        ENGINE["comfy"] = False
        if ENGINE["status"] != "error":
            ENGINE["status"] = "offline"
            ENGINE["message"] = "Engine offline."
    return web.json_response(ENGINE)


async def generate(request: web.Request) -> web.Response:
    job_id = uuid.uuid4().hex
    try:
        data, reference_images = await parse_generate_request(request, job_id)
    except Exception as exc:
        return web.json_response({"error": f"Could not read upload: {exc}"}, status=400)

    prompt = str(data.get("prompt") or "").strip()
    negative_prompt = str(data.get("negative_prompt") or "low quality, blurry, distorted, text, watermark")
    if not prompt:
        return web.json_response({"error": "Prompt is required."}, status=400)
    if ENGINE["status"] != "ready":
        return web.json_response({"error": ENGINE["message"]}, status=409)

    seed = int(data.get("seed") or int(time.time()))
    aspect = str(data.get("aspect") or "square")
    filename_prefix = str(data.get("filename_prefix") or "hidream_photo")
    keep_aspect = str(data.get("keep_aspect") or "").lower() == "true"
    workflow = build_prompt(
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect=aspect,
        seed=seed,
        filename_prefix=filename_prefix,
        reference_images=reference_images,
        keep_aspect=keep_aspect,
    )

    try:
        queued = await comfy_json(
            "POST",
            "/prompt",
            {"prompt": workflow, "client_id": f"simple-hidream-{job_id}"},
        )
    except Exception as exc:
        return web.json_response({"error": f"ComfyUI is not ready: {exc}"}, status=503)

    prompt_id = queued["prompt_id"]
    JOBS[job_id] = {
        "status": "queued",
        "prompt_id": prompt_id,
        "created": time.time(),
        "error": None,
        "filename": None,
        "subfolder": "",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect": aspect,
        "seed": seed,
        "filename_prefix": filename_prefix,
        "reference_count": len(reference_images),
        "completed_at": None,
        "duration_seconds": None,
    }
    save_jobs()
    return web.json_response({
        "job_id": job_id,
        "prompt_id": prompt_id,
        "reference_count": len(reference_images),
    })


async def job_status(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    job = JOBS.get(job_id)
    if not job:
        return web.json_response({"error": "Unknown job."}, status=404)

    payload = await refresh_job(job_id, job)
    return web.json_response(payload)


async def jobs_index(_request: web.Request) -> web.Response:
    for job_id, job in list(JOBS.items()):
        if job.get("status") not in {"done", "error"}:
            await refresh_job(job_id, job)

    jobs = [
        job_payload(job_id, job)
        for job_id, job in sorted(JOBS.items(), key=lambda item: job_created(item[1]), reverse=True)
    ]
    return web.json_response({"jobs": jobs[:MAX_HISTORY_JOBS]})


async def refresh_job(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    if job["status"] in {"done", "error"}:
        return job_payload(job_id, job)

    prompt_id = job.get("prompt_id")
    if not prompt_id:
        return job_payload(job_id, job)

    try:
        history = await comfy_json("GET", f"/history/{prompt_id}")
    except Exception as exc:
        job["status"] = "running"
        job["message"] = str(exc)
        return job_payload(job_id, job)

    item = history.get(prompt_id)
    if not item:
        job["status"] = "running"
        return job_payload(job_id, job)

    status = item.get("status", {})
    if not status.get("completed"):
        job["status"] = "running"
        return job_payload(job_id, job)

    if status.get("status_str") != "success":
        job["status"] = "error"
        job["error"] = status.get("status_str") or "Generation failed."
        save_jobs()
        return job_payload(job_id, job)

    outputs = item.get("outputs", {})
    images = outputs.get("10", {}).get("images") or outputs.get("8", {}).get("images") or []
    if not images:
        job["status"] = "error"
        job["error"] = "Generation finished, but no output image was reported."
        save_jobs()
        return job_payload(job_id, job)

    job["status"] = "done"
    job["filename"] = images[0]["filename"]
    job["subfolder"] = images[0].get("subfolder", "")
    completed_at = time.time()
    job["completed_at"] = completed_at
    created = job_created(job)
    job["duration_seconds"] = round(max(0.0, completed_at - created)) if created else None
    job.pop("message", None)
    save_jobs()
    return job_payload(job_id, job)


def job_payload(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job)
    payload["job_id"] = job_id
    if job.get("filename"):
        payload["image_url"] = f"/api/image/{job_id}?filename={job['filename']}"
    return payload


async def image(request: web.Request) -> web.FileResponse:
    job = JOBS.get(request.match_info["job_id"])
    if not job or not job.get("filename"):
        raise web.HTTPNotFound(text="Image not found.")

    subfolder = str(job.get("subfolder") or "")
    filename = Path(str(job["filename"])).name
    target = (OUTPUT_DIR / subfolder / filename).resolve()
    if OUTPUT_DIR not in target.parents and target != OUTPUT_DIR:
        raise web.HTTPForbidden(text="Invalid image path.")
    if not target.is_file():
        raise web.HTTPNotFound(text="Image file not found.")
    return web.FileResponse(target)


def create_app() -> web.Application:
    load_jobs()
    app = web.Application()
    app.on_startup.append(start_background_warmup)
    app.on_cleanup.append(stop_background_warmup)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/generate", generate)
    app.router.add_get("/api/jobs", jobs_index)
    app.router.add_get("/api/jobs/{job_id}", job_status)
    app.router.add_get("/api/image/{job_id}", image)
    return app


async def start_background_warmup(app: web.Application) -> None:
    global WARMUP_TASK
    WARMUP_TASK = asyncio.create_task(warmup_engine())
    app["warmup_task"] = WARMUP_TASK


async def stop_background_warmup(app: web.Application) -> None:
    task = app.get("warmup_task")
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def warmup_engine() -> None:
    ENGINE.update({
        "status": "starting",
        "message": "Waiting for the image engine...",
        "error": None,
        "prompt_id": None,
        "ready_at": None,
    })

    system_stats = None
    for _ in range(120):
        try:
            system_stats = await comfy_json("GET", "/system_stats")
            ENGINE["comfy"] = True
            break
        except Exception:
            ENGINE["comfy"] = False
            await asyncio.sleep(1)
    else:
        ENGINE.update({
            "status": "error",
            "message": "ComfyUI did not start.",
            "error": "ComfyUI did not start.",
        })
        return

    if system_stats is not None and model_is_resident(system_stats):
        mark_ready("Engine ready. Model was already loaded.")
        return

    ENGINE.update({
        "status": "warming",
        "message": "Warming HiDream model into GPU memory...",
    })

    try:
        object_info = await comfy_json("GET", "/object_info")
        if "SimpleHiDreamWarmup" not in object_info:
            raise RuntimeError("Warmup node was not loaded by ComfyUI.")

        queued = await comfy_json(
            "POST",
            "/prompt",
            {"prompt": build_warmup_prompt(), "client_id": "simple-hidream-warmup"},
        )
        prompt_id = queued["prompt_id"]
        ENGINE["prompt_id"] = prompt_id

        started = time.time()
        while True:
            elapsed = int(time.time() - started)
            ENGINE["message"] = f"Warming HiDream model into GPU memory... {elapsed}s"
            try:
                history = await comfy_json("GET", f"/history/{prompt_id}")
            except Exception:
                await asyncio.sleep(5)
                continue

            item = history.get(prompt_id)
            if not item:
                await asyncio.sleep(5)
                continue

            status = item.get("status", {})
            if status.get("completed") and status.get("status_str") == "success":
                mark_ready()
                return

            if status.get("completed"):
                raise RuntimeError(status.get("status_str") or "Warmup failed.")

            await asyncio.sleep(5)
    except Exception as exc:
        ENGINE.update({
            "status": "error",
            "message": f"Warmup failed: {exc}",
            "error": str(exc),
        })


if __name__ == "__main__":
    web.run_app(create_app(), host=APP_HOST, port=APP_PORT)
