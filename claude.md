# Immich Manager - Future Features & Ideas

---

## Current Status (as of 2026-03-18)

### What's Working
- Immich running via Docker (4 containers: server, ml, postgres, redis)
- Server Manager installed at `/opt/immich-server-manager`, running on port 8080
- Photo Curator installed at `/opt/photo-curator`, running on port 8081
- Cloudflare Tunnel running (`immich.houseoffeuer.com` confirmed working)
- Security hardening complete (fail2ban, UFW)
- Immich SSO auth working in photo curator (cookie-based via `immich_access_token`)

### Known Issues to Debug Tomorrow

#### 1. Photo Curator — Photos Not Loading from Immich
- The curator UI loads and auth works
- Photos are not being fetched/displayed from Immich
- Likely causes to investigate:
  - Check `GET /api/photos` endpoint in photo-curator — does it correctly call Immich API?
  - Verify the Immich API key in `/opt/photo-curator/config/config.yaml` is valid
  - Check for errors in `sudo journalctl -u photo-curator -f` when navigating to photos
  - The `ImmichClient` in `photo-curator/src/immich_client.py` — verify it uses the correct API endpoints for the installed Immich version
  - Batch processing was disabled at startup due to "no admin API key" — verify the key was saved correctly after the config edit

#### 2. Photo Curator — Crashes
- Service crashes intermittently
- Start debugging with: `sudo journalctl -u photo-curator -n 100 --no-pager`
- Look for the stack trace just before the crash

#### 3. Caddy Reverse Proxy — NOT YET IMPLEMENTED
- **This is the next infrastructure task**
- Goal: put all services behind Caddy on port 80 so they share cookie scope
- Plan:
  - Create `docker/proxy.yml` with Caddy container on the homelab network
  - Create `docker/caddy/Caddyfile` with path-based routing:
    - `localhost/` → Immich (`immich-server:2283` via Docker network)
    - `localhost/curator/` → Photo Curator (`host.docker.internal:8081`)
    - `localhost/monitor/` → Server Manager (`host.docker.internal:8080`)
  - Add `extra_hosts: ["host.docker.internal:host-gateway"]` to Caddy service so it can reach host systemd services
  - Update Cloudflare tunnel to point to `localhost:80` instead of individual ports
  - Update photo-curator and server-manager uvicorn launch with `--root-path` flag
  - Update all JS `fetch()` calls in `curator.html` to use a configurable `window.API_BASE`
  - See `docker/core.yml` for the existing Caddy placeholder config

### Installation Bugs Fixed (so future installs won't hit these)
- `python3-venv` not installed → added to prerequisites quick-fix command
- `cmake` + `build-essential` not installed → added to Phase 2 before ML pip installs
- `libgl1-mesa-glx` renamed to `libgl1` in Ubuntu 24.04 → fixed in Phase 2
- `shared/` module not copied to install dirs → fixed in Phase 1 and Phase 2 scripts
- `cp -r shared /dest/shared` creates `shared/shared` if dest exists → fixed with `mkdir -p` + `cp -r shared/. /dest/shared/`
- Install state file in `/tmp` (lost on reboot) → moved to `~/.immich-install-state.json`
- Phase 0 re-runs when Phase 1 is already complete → install.sh now skips Phase 0 if Phase 1 is marked complete
- `psutil` and `python-multipart` missing from photo-curator requirements → added
- FastAPI dependency returning HTMLResponse instead of raising exception → fixed with `NotAuthenticatedException` + exception handler
- Immich auth token validation used wrong endpoint (`/api/auth/validateToken` → 404) → fixed to use `/api/users/me`

---

This document tracks feature ideas and improvements for future implementation.

## Features Saved for Later Implementation

### 6. Event Auto-Detector with Manual Sharing Flow

**Purpose**: Detect events from photo metadata and suggest (never auto-create) shared albums

**Features**:
- Detect events from clustering of photos by:
  * Time proximity (multiple photos within short time span)
  * Location proximity (GPS data clustering)
  * Face detection (same people appear in multiple photos)
  * Upload patterns (multiple users upload photos on same dates)
- Suggest event names based on:
  * Location data ("Trip to San Francisco")
  * Date patterns ("Birthday Party - March 2024")
  * Photo volume ("Weekend Getaway")
- Show suggestions in curator dashboard
- Manual confirmation required for ALL actions
- Sharing workflow:
  1. System detects potential event
  2. Shows suggestion card: "Looks like you had an event on March 15!"
  3. User clicks "Review"
  4. System shows photos + detected participants (by face recognition)
  5. User can:
     - Create personal album (no sharing)
     - Create shared album and manually invite specific users
     - Dismiss suggestion
- Never automatically share photos across users

**Implementation Notes**:
```python
# Event detection algorithm
def detect_events(user_id: str, year: int, month: int) -> List[EventSuggestion]:
    photos = get_photos_with_metadata(user_id, year, month)

    # Cluster by time (photos within 4 hours = same event)
    time_clusters = cluster_by_timestamp(photos, max_gap_hours=4)

    # Further cluster by location if GPS available
    for cluster in time_clusters:
        if has_gps_data(cluster):
            location_clusters = cluster_by_location(cluster, max_distance_km=1)

    # Detect participants via face detection
    for event in events:
        event.participants = detect_faces_across_photos(event.photos)
        # Match faces to known users in family (if permission granted)

    # Generate event names
    for event in events:
        event.suggested_name = generate_event_name(
            event.date,
            event.location,
            event.photo_count,
            event.participants
        )

    return events
```

**UI Design**:
- Event suggestion cards in curator dashboard
- "Review Event" button opens modal
- Photo grid showing all detected event photos
- Detected participants (faces, not names unless user has granted permission)
- Three action buttons:
  1. "Create Personal Album" - no sharing
  2. "Create & Share" - opens participant selector
  3. "Dismiss"

**Privacy Considerations**:
- Event detection runs per-user, not cross-user
- Face matching only within user's own photo library
- Sharing requires explicit user action
- Users can disable event detection in preferences
- No automatic notifications to other users
- Cross-user event detection requires:
  * Admin opt-in feature flag
  * Multiple users opt-in to cross-user detection
  * Clear privacy policy displayed

**Admin Settings**:
```yaml
event_detection:
  enabled: true  # Enable/disable globally
  min_photos: 5  # Minimum photos to suggest an event
  max_gap_hours: 4  # Maximum time gap within event
  cross_user_detection: false  # Allow detecting multi-user events
  require_user_optin: true  # Users must opt-in
```

**User Preferences**:
```yaml
event_detection:
  enabled: true/false  # Show event suggestions
  auto_detect: true/false  # Run detection automatically
  cross_user_participation: false  # Allow cross-user event detection
```

**Security**:
- Event suggestions are per-user
- Sharing requires explicit action
- No photo data shared without user confirmation
- Face detection data never crosses user boundaries
- Users can see who else uploaded to same event ONLY if:
  * They explicitly create shared album
  * Other users accept sharing invitation

**TODO: Spec Needed from User**:
1. Should cross-user event detection be supported at all?
   - If yes: How to handle privacy/permissions?
   - If no: Keep it strictly per-user suggestions
2. Face recognition for participant detection?
   - Immich has built-in face detection
   - Should we use it for event suggestions?
3. Sharing invitation workflow?
   - Email invitations?
   - In-app notifications?
   - Both?
4. Event categories/types?
   - Birthdays, Holidays, Trips, Daily life, etc.
   - Custom categories?

---

### 7. Memory Lane / Automated Memories

**Purpose**: Create engaging nostalgic experiences with automated memory compilations

**Features**:
- "On This Day" X years ago automatic album suggestions
- Monthly/yearly memory compilations
- Slideshow generation with background music
- Email "Your Month in Photos" summaries (user opt-in)
- Seasonal memories (e.g., "Summer 2023" automatically surfaces)
- Milestone detection (first photo of baby, graduations, weddings)

**Implementation Notes**:
- Query photos by date ranges (today's date, different years)
- Use AI scores to select best photos from those dates
- Respect user email preferences (opt-in only)
- Never automatically share - only suggest to individual users
- Create draft albums that users can review/accept

**Privacy Considerations**:
- Memories are per-user, never cross-user without explicit sharing
- Email notifications must be opt-in via user preferences
- Users can disable specific memory types

---

### 8. Smart Sharing Suggestions

**Purpose**: Suggest (but never auto-share) photos to relevant family members

**Features**:
- Detect photos with specific people, suggest sharing with them
- "John was at this event but has 0 photos - share yours?" prompts
- Face-based sharing suggestions (privacy-safe)
- Suggest creating shared albums for events (manual confirmation required)

**Implementation Notes**:
- **CRITICAL**: NEVER automatically share photos
- Only provide suggestions in UI with explicit "Share" button
- Require user confirmation for every share action
- Track who attended events via photo metadata + face detection
- Use existing face detection from analyzer.py

**Privacy Considerations**:
- Suggestions only, never automatic sharing
- Users can disable suggestions in preferences
- Face detection data stays local, never shared
- Explicit consent required for every share action

---

### 13. Photo Quality Alerts

**Purpose**: Proactively help users improve photo quality

**Features**:
- Alert when photos consistently blurry (dirty lens suggestion)
- Low exposure warnings with tips
- Device-specific issue detection ("iPhone 12 photos are dark lately")
- Suggest camera settings improvements
- Weekly quality report (optional email, user opt-in)

**Implementation Notes**:
- Extend existing analyzer.py quality scoring
- Track quality trends per user over time
- Store in database: user_id, device, avg_quality, timestamp
- Generate friendly suggestions, not technical errors
- Email alerts must be opt-in via user preferences

**User Preferences**:
```yaml
quality_alerts:
  enabled: true/false
  email_notifications: true/false
  min_quality_threshold: 0.5
  alert_frequency: "weekly" | "monthly" | "never"
```

---

### 15. Seasonal Automations

**Purpose**: Timely, relevant photo automation that builds family traditions

**Features**:
- December: "Create 'Year in Review' album?" suggestion
- Birthdays: Auto-suggest "Birthday [Name] 2024" albums (manual creation)
- Holidays: Suggest holiday cards from best photos
- Back to school: "First Day of School" yearly comparison
- Anniversary reminders with photo suggestions
- Seasonal transitions: "Best of Summer 2024" suggestions

**Implementation Notes**:
- Cron jobs check dates daily
- Generate suggestions, never auto-create albums
- Respect user preferences for which automations to enable
- Email reminders are opt-in only
- UI shows pending suggestions with dismiss option

**User Preferences**:
```yaml
seasonal_automations:
  year_in_review: true/false
  birthday_albums: true/false
  holiday_suggestions: true/false
  anniversary_reminders: true/false
  email_notifications: true/false
```

**Privacy & UX**:
- Suggestions appear in curator dashboard, not as emails (unless user opts in)
- One-click dismiss for suggestions user doesn't want
- Never create albums automatically - always manual confirmation
- Track user's timezone for accurate date-based triggers

---

## Implementation Principles for All Features

### Privacy First
1. **Never auto-share photos between users** - always require explicit confirmation
2. **All email notifications are opt-in** - default to disabled
3. **Face detection data stays local** - never shared across user boundaries
4. **User data isolation** - each user sees only their data unless explicitly shared

### Email Preferences Architecture
```python
# user-preferences table
{
    "user_id": "uuid",
    "email_notifications": {
        "monthly_reminders": false,
        "quality_alerts": false,
        "memory_lane": false,
        "seasonal_automations": false,
        "storage_warnings": true,  # Critical alerts default true
        "backup_reports": false
    },
    "ui_suggestions": {
        "sharing_suggestions": true,
        "event_detection": true,
        "duplicate_warnings": true
    }
}
```

### Admin Settings Architecture
```yaml
# admin-config.yaml
email:
  enabled: true  # Master switch - disables ALL emails if false
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  smtp_user: "admin@example.com"
  smtp_password: "password"

features:
  memory_lane: true  # Enable/disable feature globally
  seasonal_automations: true
  quality_alerts: true
  sharing_suggestions: true

defaults:
  # Default preferences for new users
  email_notifications:
    monthly_reminders: false
    quality_alerts: false
```

### Styling Consistency
- **Use Tailwind CSS** for all new UIs
- **Match Immich design system**:
  - Primary: `#4250af`
  - Dark mode: True black `#000000`
  - Gray scale: `immich-gray-{50-900}`
- **Component patterns**:
  - Card-based layouts with borders
  - Rounded corners (8-12px)
  - Subtle shadows in light mode, none in dark
  - Hover states with scale/shadow transitions
- **Icons**: Material Design icon style (SVG)
- **Responsive**: Mobile-first, use Tailwind breakpoints

---

## Feature Priority Matrix

### High Impact, Low Effort (Do First)
- Load actual thumbnails ✓ (In Progress)
- Keyboard shortcuts ✓ (In Progress)
- Duplicate detection UI ✓ (In Progress)

### High Impact, Medium Effort (Do Next)
- Monthly email reminders ✓ (In Progress)
- Storage usage dashboard ✓ (In Progress)
- Event auto-detector ✓ (In Progress)

### High Impact, High Effort (Saved for Later)
- Memory Lane (#7)
- Seasonal Automations (#15)
- Smart Sharing Suggestions (#8)

### Medium Impact (Nice to Have)
- Photo Quality Alerts (#13)
- Analytics improvements
- Advanced backup testing

---

## Notes & Decisions

**Date**: 2025-11-22

**Key Decisions**:
1. All photo sharing requires explicit user action - no automation
2. Email preferences are per-user and opt-in by default
3. Admin can disable features globally, but can't force-enable user emails
4. Tailwind CSS + Immich design system for all new UIs
5. Privacy-first: user data isolation is paramount

**Implementation Order**:
1. Quick wins (thumbnails, keyboard shortcuts, duplicates)
2. Storage & event detection (medium complexity)
3. Migration & health tools (admin value)
4. Analytics dashboard (insights)
5. Future features (memories, seasonal, sharing suggestions)

---

## Related Documentation

- See `photo-curator/README.md` for curator-specific features
- See `server-manager/README.md` for monitoring features
- See `docs/PRIVACY.md` for privacy policy details
- See `docs/USER-PREFERENCES.md` for preference configuration
