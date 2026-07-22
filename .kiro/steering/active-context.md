---
inclusion: always
---

# Active Context - Current Task State

## Current Focus
3D Print Library v2 COMPLETE — unified app with Viewer + Sorter merged. All spec tasks executed successfully.

## Recent Changes
- All unified-library spec tasks completed
- config.py: shared config module (load/save, resolve paths)
- categories.py: 8-step name cleanup + keyword categorization + load/save
- sorter.py: 5-phase sync pipeline (ZIP, index, categorize, move, clean)
- server.py: extended with sync API, scheduler, config/categories endpoints, setup wizard
- sync.html + sync.js: sync control panel + category editor
- setup.html: first-run wizard (starter / existing / blank modes)
- Edge-case hardening: EC-1 through EC-28 implemented
- README updated with combined-app usage

## Upcoming Changes
- First real-user test of the unified app (ingest + browse)
- Potential v3 features: interactive 3D viewer, bulk tag editor, AI auto-tagging
- Dark mode toggle
- Keyboard navigation

## Active Decisions and Considerations
- v2 is complete and functional — focus shifts to real-world usage feedback
- STL thumbnails will render progressively as user browses (first-time only, then cached)
- 265 of 688 files already have thumbnails from 3MF extraction — instant on first load
- Sync scheduler uses shared lock with scanner — non-reentrant, prevents collisions
