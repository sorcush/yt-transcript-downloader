# Command Bar Redesign

**Date:** 2026-03-26
**Status:** Approved

## Problem

The top of the UI has three stacked rows before the table appears:
1. URL input + Fetch button
2. Output folder + Browse + Cookies dropdown
3. Status / date-fetch indicator row

This wastes vertical space and the status row adds visual clutter even when idle.

## Solution

Collapse all three rows into a single command bar. The status indicators become inline chips that always occupy space (preventing layout shift) but are only visible when relevant.

## Layout

Single row, left to right:

| Element | Type | Behavior |
|---|---|---|
| URL input | `<input type="text">` | `flex: 2`, min-width 0 |
| Fetch button | `<button>` | Always visible |
| "✓ N fetched" chip | `<span>` | `visibility: hidden` before first fetch; visible after |
| "Dates X/N ✕" chip | `<span>` | `visibility: hidden` when not streaming dates; visible while `/api/dates` stream is active; ✕ inside chip cancels the stream |
| Folder path input | `<input type="text">` | `flex: 1`, min-width 0 |
| Browse button | `<button>` | Always visible |
| Browser dropdown | `<select>` | Always visible |

## Key Constraint: No Layout Shift

The two chips are **always rendered** in the DOM and always occupy their layout space. They toggle between `visibility: hidden` and `visibility: visible` — never `display: none`. This keeps the folder/Browse/dropdown at fixed positions regardless of fetch state.

## Elements Removed

- `#info-row` div (the old status bar row)
- `#status-bar` span
- `#date-status` span and its wrapper
- `#date-stop-btn` (stop functionality moves into the dates chip's ✕)

## Chip States

**Fetched chip** (`#fetched-chip`):
- Hidden: before any fetch
- Visible: `✓ {N} fetched` after `/api/fetch` completes

**Dates chip** (`#dates-chip`):
- Hidden: before fetch, and after dates stream completes or is stopped
- Visible: `Dates {loaded}/{total} ✕` while `/api/dates` stream is active
- ✕ click aborts `state.dateAbort` (same as current stop button)

## Files Changed

- `frontend/index.html` — replace rows 2 and 3 with chip elements inside the existing `.input-row`
- `frontend/app.js` — update DOM refs, `setStatus`, `fetchDatesLazy`, `updateDateCell` to use chips instead of `#info-row`
- `frontend/style.css` — add chip styles, remove `#info-row` / `#date-status` styles
