# Command Bar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the three stacked top rows (URL bar, folder row, status row) into a single command bar with inline status chips that never shift the layout.

**Architecture:** All controls live in one `.input-row` flex container. Two chips — fetched and dates — are always rendered with `visibility: hidden/visible` (never `display: none`) so positions stay stable. The fetched chip doubles as a general status display. The old `#info-row` and its children are removed entirely.

**Tech Stack:** Vanilla JS, HTML, CSS — no build step. No frontend test framework exists; verification is manual browser checks.

---

### Task 1: Restructure index.html

**Files:**
- Modify: `frontend/index.html`

The goal is to replace the three top rows with one `.input-row` containing all controls, including the two always-present chips.

- [ ] **Step 1: Replace the three top rows with a single command bar**

Open `frontend/index.html`. Replace lines 18–50 (the two `.input-row` divs and the `#info-row` div) with:

```html
<!-- Single command bar -->
<div class="input-row">
  <input id="url-input" type="text"
         placeholder="Paste YouTube URL (video, playlist, or channel)">
  <button id="fetch-btn">Fetch</button>
  <span id="fetched-chip" class="status-chip"></span>
  <span id="dates-chip" class="status-chip">
    <span id="dates-chip-text"></span>
    <button id="dates-stop-btn" class="chip-stop">✕</button>
  </span>
  <input id="output-folder" type="text"
         placeholder="Output folder">
  <button id="browse-btn" type="button">Browse</button>
  <select id="browser-select">
    <option value="">None</option>
    <option value="chrome" selected>Chrome</option>
    <option value="firefox">Firefox</option>
    <option value="safari">Safari</option>
    <option value="edge">Edge</option>
    <option value="brave">Brave</option>
    <option value="chromium">Chromium</option>
  </select>
</div>
```

- [ ] **Step 2: Verify the old rows are gone**

Confirm that `#info-row`, `#status-bar`, `#date-status`, `#date-status-text`, and `#date-stop-btn` no longer appear anywhere in `index.html`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: replace stacked rows with single command bar"
```

---

### Task 2: Update CSS

**Files:**
- Modify: `frontend/style.css`

Add chip styles. Remove the old `#info-row` / `#date-status` block.

- [ ] **Step 1: Remove old info-row and date-status styles**

Delete this entire block from `style.css` (lines 90–124):

```css
#info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  background: #1e1e2e;
  border: 1px solid #313244;
  color: #a6adc8;
}

#status-bar { color: #a6adc8; }
#status-bar:empty { display: none; }
#status-bar.error { color: #f38ba8; }

#date-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: #a6adc8;
}

#date-stop-btn {
  background: transparent;
  border: 1px solid #45475a;
  color: #f38ba8;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
}

#date-stop-btn:hover { background: #3a1e1e; border-color: #f38ba8; }
```

- [ ] **Step 2: Add chip and chip-stop styles**

Add the following after the `select:focus { border-color: #cba6f7; }` line:

```css
.status-chip {
  visibility: hidden;
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  color: #a6adc8;
  white-space: nowrap;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.status-chip.visible { visibility: visible; }
.status-chip.error { color: #f38ba8; border-color: #f38ba8; }

.chip-stop {
  background: transparent;
  border: none;
  color: #f38ba8;
  font-size: 12px;
  font-weight: 700;
  padding: 0;
  cursor: pointer;
  line-height: 1;
}

.chip-stop:hover { color: #ff7f7f; background: transparent; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/style.css
git commit -m "feat: add status chip styles, remove info-row styles"
```

---

### Task 3: Update app.js

**Files:**
- Modify: `frontend/app.js`

Update DOM refs, `setStatus`, `init`, `fetchDatesLazy`, and clear the `setStatus` calls that referenced the old elements.

- [ ] **Step 1: Replace removed DOM refs with new chip refs**

In `app.js`, replace lines 22–34 (the old `infoRow`, `statusBar`, `dateStatus`, `dateStatusText`, `dateStopBtn` refs):

```js
const fetchedChip    = document.getElementById('fetched-chip');
const datesChip      = document.getElementById('dates-chip');
const datesChipText  = document.getElementById('dates-chip-text');
const datesStopBtn   = document.getElementById('dates-stop-btn');
```

- [ ] **Step 2: Update the dateStopBtn listener in init()**

Replace:
```js
dateStopBtn.addEventListener('click', () => {
  if (state.dateAbort) state.dateAbort.abort();
});
```
With:
```js
datesStopBtn.addEventListener('click', () => {
  if (state.dateAbort) state.dateAbort.abort();
});
```

- [ ] **Step 3: Rewrite setStatus()**

Replace the entire `setStatus` function (lines 282–287):

```js
// ── Status display ──────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
  fetchedChip.textContent = msg;
  fetchedChip.classList.toggle('error', isError);
  fetchedChip.classList.add('visible');
}
```

- [ ] **Step 4: Update handleFetch() to show fetched count on the chip**

In `handleFetch()`, replace:
```js
setStatus(`Fetched ${data.videos.length} video(s)`);
```
With:
```js
fetchedChip.textContent = `✓ ${data.videos.length} fetched`;
fetchedChip.classList.remove('error');
fetchedChip.classList.add('visible');
```

- [ ] **Step 5: Rewrite fetchDatesLazy() to use datesChip**

Replace the entire `fetchDatesLazy` function:

```js
async function fetchDatesLazy(videos) {
  if (state.dateAbort) state.dateAbort.abort();

  const needsDates = videos.filter(v => !v.upload_date);
  if (needsDates.length === 0) return;

  const total = needsDates.length;
  let loaded = 0;

  state.dateAbort = new AbortController();
  datesChipText.textContent = `Dates 0/${total}`;
  datesChip.classList.add('visible');

  try {
    const res = await fetch('/api/dates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ videos: needsDates.map(v => ({ video_id: v.video_id, url: v.url })), cookies_browser: browserSelect.value || null }),
      signal: state.dateAbort.signal,
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const { video_id, upload_date } = JSON.parse(line.slice(6));
          updateDateCell(video_id, upload_date);
          loaded++;
          datesChipText.textContent = `Dates ${loaded}/${total}`;
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') console.error('Date fetch error:', err);
  } finally {
    datesChip.classList.remove('visible');
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app.js
git commit -m "feat: wire command bar chips, remove info-row JS"
```

---

### Task 4: Manual verification

**Files:** none

- [ ] **Step 1: Start the server**

```bash
cd /Users/sandrey/Dev/youtube-automation
./run.sh
```

Open `http://localhost:8000` in a browser.

- [ ] **Step 2: Check initial state — no layout shift baseline**

Before clicking anything:
- Both chips should be invisible but occupying space
- Folder, Browse, and browser dropdown should be at fixed positions on the right
- No extra rows below the command bar

- [ ] **Step 3: Paste a URL and click Fetch**

After fetch completes:
- Fetched chip appears: `✓ N fetched`
- Dates chip appears while streaming: `Dates X/N` with ✕
- Folder/Browse/dropdown must NOT shift — measure visually
- Dates chip disappears after stream ends

- [ ] **Step 4: Click ✕ while dates are streaming**

Dates chip should disappear immediately after cancellation.

- [ ] **Step 5: Click Browse**

Fetched chip updates to `Output folder set to …` — folder/Browse/dropdown stay at same positions.

- [ ] **Step 6: Commit if all checks pass**

```bash
git add -p  # nothing to stage — this is a verification task
```

No commit needed for this task.
