# Adding Features — Documentation Guide

This guide tells you (and Claude) exactly what docs to update when a new feature is added to Immich Manager, so you can always track what's built and validate that it works.

---

## The Rule: Every Feature Gets a FEATURES.md Entry

`FEATURES.md` is the canonical list of what exists. **If it's not in there, it doesn't count as done.**

When Claude (or you) implements a feature:
1. Add a `FEATURES.md` entry — before or immediately after the code is written
2. Update any relevant config reference in `SETUP.md`
3. Update `README.md` roadmap bullet if it was listed as planned

---

## Required Entry Format for FEATURES.md

Copy this template for each new feature:

```markdown
### ✅ Feature Name
**Component:** `directory/filename.py` (or component name like `server-manager`)
**Config:** `path/to/config.yaml` → `section.key` (omit if no config)
**API:** `METHOD /api/endpoint` (omit if no API)

One or two sentences describing what the feature does and why it exists.

**Validate:**
```bash
# Commands to confirm the feature is actually working
# Be specific — use real API calls, log grep patterns, or UI steps
curl http://localhost:8080/api/example | jq '.result'
sudo journalctl -u immich-server-manager | grep "Feature Name"
```
```

### Checklist before marking ✅

- [ ] Code is written and deployed
- [ ] `FEATURES.md` entry added with working validate commands
- [ ] Config documented in `SETUP.md` if the feature requires configuration
- [ ] API endpoints documented in `API.md` if new routes were added
- [ ] Component `README.md` updated if the feature belongs to a specific component

---

## Which Doc Gets Updated for What

| What changed | Update these docs |
|-------------|-------------------|
| New feature implemented | **FEATURES.md** (required), README.md roadmap |
| New API endpoint | **API.md** + FEATURES.md entry |
| New config option | **SETUP.md** + FEATURES.md entry |
| New component/service | component `README.md` + ARCHITECTURE.md + FEATURES.md |
| New Docker service | **docs/DOCKER.md** |
| Bug fix only | No doc update needed unless behavior changed |
| Planned feature removed | Remove from FEATURES.md planned table + README roadmap |

---

## Telling Claude Where to Look

When asking Claude to add a feature, give it context upfront so it doesn't have to search:

**Good prompt pattern:**
> "Add X feature to the photo-curator component. The main entry point is `photo-curator/src/main.py`. Config lives in `photo-curator/config/config.yaml`. When done, update FEATURES.md and SETUP.md."

**Reference docs to include:**
- Point Claude at `FEATURES.md` to see what already exists and avoid duplication
- Point Claude at `SETUP.md` to match existing config patterns
- Point Claude at `API.md` if adding new endpoints (so it can follow existing response format)
- Point Claude at `ARCHITECTURE.md` if the feature involves a new component or major data flow

---

## Validation Strategy

Every feature entry in `FEATURES.md` must have validate commands that can be run against a live instance to confirm the feature works end-to-end. Follow these patterns:

**For API features:**
```bash
curl http://localhost:8080/api/your-endpoint | jq '.key_field'
# Expected: a real value, not null or empty
```

**For background jobs (schedulers, timers):**
```bash
sudo journalctl -u service-name | grep "job name"
# Expected: log line confirming the job ran
```

**For UI features:**
```
1. Navigate to http://localhost:8081/page-name
2. Verify X element is visible
3. Click Y and confirm Z happens
```

**For systemd services:**
```bash
sudo systemctl status service-name
# Expected: active (running)
```

**For config-dependent features:**
```bash
# Always test with a real config value, then verify the behavior changes
```

---

## Feature Lifecycle

```
📋 Planned  →  🔄 In Progress  →  ✅ Implemented
(FEATURES.md     (move symbol,     (move to correct
planned table)    add code files)    section + validate)
```

1. **Planned:** Feature is in the planned table at the bottom of `FEATURES.md`
2. **In progress:** Move it out of the planned table into the appropriate section with `🔄` status; add code location
3. **Implemented:** Change `🔄` to `✅`; add real validate commands; update any config docs

---

## Example: Adding a New Feature End-to-End

**Scenario:** Adding a "Storage Usage Dashboard" to the Photo Curator.

**Step 1 — Add to FEATURES.md while building:**

```markdown
### 🔄 Storage Usage Dashboard
**Component:** `photo-curator`
**API:** `GET /api/storage`
**Access:** `/storage` page

Shows per-user storage consumption with breakdown by media type.
```

**Step 2 — After implementation, update to ✅ and add validation:**

```markdown
### ✅ Storage Usage Dashboard
**Component:** `photo-curator`
**API:** `GET /api/storage`
**Access:** `/storage` page (Immich SSO required)

Shows per-user storage consumption with breakdown by media type (photos, videos, raw files).

**Validate:**
```bash
curl http://localhost:8081/api/storage \
  -H "Cookie: immich_access_token=YOUR_TOKEN" | jq '.users[0]'
# Should return {user_id, total_gb, photos_gb, videos_gb}
```
```

**Step 3 — Update SETUP.md if it needs config:**

Add to the "Feature Configuration" section in `SETUP.md`:
```markdown
### Storage Usage Dashboard
**Status:** Implemented, no configuration needed
```

**Step 4 — Update README.md roadmap:**

Move "Storage usage dashboard" from Planned to Completed in the README roadmap bullets.

---

## Notes for Claude Specifically

- When asked to "add a feature," always check `FEATURES.md` first to see if it already exists
- When a feature is complete, update `FEATURES.md` in the same PR/commit as the code
- Validate commands must be real commands that can be copy-pasted and run — not pseudocode
- If a feature has no testable output yet (e.g., a planned cron job), note that in the validate section and mark it `🔄` until it can be confirmed
- Keep feature descriptions short (1–2 sentences) — the detail lives in `API.md`, `ARCHITECTURE.md`, and component READMEs
