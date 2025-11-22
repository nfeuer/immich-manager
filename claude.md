# Immich Manager - Future Features & Ideas

This document tracks feature ideas and improvements for future implementation.

## Features Saved for Later Implementation

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
