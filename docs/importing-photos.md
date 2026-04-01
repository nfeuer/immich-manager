# Importing Photos into Immich

## Quick Reference

| Method | Best for | Cloudflare-safe | Resume support |
|---|---|---|---|
| Browser upload | < ~500 photos, one-off imports | No (100 MB limit) | No |
| Server-path import | 1,000–20,000+ photos | Yes (local only) | Yes |
| Google Takeout | Full Google Photos migration | No (large) | Yes |
| Apple / iCloud | Apple Photos or iCloud export | No (large) | Yes |

---

## Browser Upload

Use the **Import** page in the curator UI, select your source, drag a folder or pick files, and click **Start Import**.

**Cloudflare free tier limitation:** Cloudflare's free plan enforces a 100 MB per-request limit. Uploading large collections through the Cloudflare tunnel will fail. Use server-path import instead for anything over a few hundred photos.

---

## Server-Path Import (Large Collections)

For large imports (1,000+ photos), copy files to the server first and import directly from the server filesystem — nothing passes through the browser or Cloudflare.

### Step 1 — Copy photos to the server

```bash
# Sync a folder to the server, preserving structure
rsync -avz --progress /local/path/to/Wedding\ Photos/ user@your-server:/opt/photos-import/Wedding\ Photos/

# Verify it landed correctly
ssh user@your-server ls /opt/photos-import/
```

### Step 2 — Access the curator locally

Open an SSH tunnel to bypass Cloudflare:

```bash
ssh -L 8081:localhost:8081 user@your-server
```

Then open `http://localhost:8081` in your browser. If you are already on the server, open it directly.

### Step 3 — Start the import

1. Go to **Import** → **Server Path (Large Import)**
2. Enter the server path, e.g. `/opt/photos-import/Wedding Photos`
3. Select **Plain folder** as the source format
4. Optionally enable **Create albums from subfolders** (see below)
5. Click **Start Import** and watch progress in real time

### Resume

If the import is interrupted, restart it with the same server path. Files already uploaded are tracked in `folder-import-progress.json` inside the import directory and skipped automatically.

Check the server manager log viewer for `[Import:folder] Batch N/M` lines to see where the previous run stopped.

---

## Folder Album Creation

When importing a folder that contains subfolders, the curator can automatically create Immich albums named after those subfolders.

### How it works

Every subfolder at any depth becomes its own album. A photo is added to **all** albums in its path.

**Example — importing `Wedding Photos/`:**

```
Wedding Photos/
├── Venue/
│   ├── hall.jpg        → album: Venue
│   └── garden.jpg      → album: Venue
├── Ceremony/
│   ├── vows.jpg        → album: Ceremony
│   └── Church/
│       └── exterior.jpg → albums: Ceremony AND Church
└── toast.jpg           → no album (loose file in root)
```

Albums created: **Venue**, **Ceremony**, **Church**

The root folder (`Wedding Photos`) is not created as an album by default.

### Root folder toggle

Enable **"Add loose photos to a 'Wedding Photos' album"** to collect photos sitting directly in the root folder into an album named after that folder. The toggle only appears after enabling **Create albums from subfolders**.

### Resume and album assignments

Album assignments are flushed to Immich every 25 files. If an import is interrupted, restarting it will:
- Skip already-uploaded files (via the progress file)
- Re-assign newly uploaded files to albums correctly

Files that were uploaded in the previous run and successfully flushed to albums in the previous run are already in their albums and do not need to be re-added. At most one unflushed batch (up to 24 files) may not be re-added on resume.

---

## Google Photos Import

1. Request a Google Takeout at [takeout.google.com](https://takeout.google.com) — select Google Photos only
2. Download and extract the archive on the server
3. For large exports, use **Server Path** import with source format set to **Google Takeout export**

Google Takeout preserves original capture dates via `.json` sidecar files. The importer reads these automatically.

---

## Apple Photos / iCloud Import

**Apple Photos:** In the Photos app, select all photos → **File → Export → Export Originals**. Import using the **Apple Photos** source.

**iCloud:** Request your data at [privacy.apple.com](https://privacy.apple.com). Select iCloud Photos. Use the **iCloud** source when importing.

---

## Troubleshooting

**Photos appear with wrong or missing dates**
The importer reads EXIF `DateTimeOriginal` first, then falls back to file modification time. If dates are still wrong, use `exiftool` to stamp them before importing:
```bash
exiftool -DateTimeOriginal'<${FileModifyDate}' -overwrite_original /path/to/photos/
```

**"Server path does not exist" error**
The path must exist on the server running the curator, not your local machine. Verify with:
```bash
ssh user@your-server ls /opt/photos-import/
```

**Import stops partway through**
Restart with the same path — already-uploaded files are skipped. Check the **server manager log viewer** for `[Import:folder]` batch lines to diagnose where it stopped.

**Cloudflare error during browser upload**
Switch to server-path import. Cloudflare free tier rejects uploads over 100 MB per request.
