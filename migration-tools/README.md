# Migration Tools

Tools for importing photos from various services into Immich.

| Script | Source | Metadata |
|--------|--------|----------|
| `google-photos-import.py` | Google Takeout export | JSON sidecar files |
| `apple-photos-import.py` | Apple Photos.app export | Embedded EXIF |
| `icloud-import.py` | iCloud data export (privacy.apple.com) | Embedded EXIF + directory names |

---

## Prerequisites (all importers)

1. **Python 3.9+**
2. **Immich API Key** — Immich → Settings → API Keys → Create
3. **Install dependencies:**
   ```bash
   cd migration-tools
   pip install -r requirements.txt
   ```

---

## Google Photos Import

Import your complete Google Photos library into Immich while preserving:
- Original capture dates
- GPS location data
- Album structure
- Photo descriptions

### Prerequisites

1. **Google Takeout Export**
   - Go to: https://takeout.google.com
   - Select only "Google Photos"
   - Choose export format: .zip
   - File size: Maximum (50GB recommended for fewer files)
   - Download and extract the ZIP file

2. **Immich API Key**
   - Open Immich web interface
   - Settings → API Keys → Create
   - Copy the API key

3. **Python Dependencies**
   ```bash
   cd migration-tools
   pip install -r requirements.txt
   ```

### Usage

**Basic Import:**
```bash
python google-photos-import.py \
  --takeout-dir ~/Downloads/Takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY
```

**Resume Interrupted Import:**
Progress is automatically saved. Just run the same command again:
```bash
python google-photos-import.py \
  --takeout-dir ~/Downloads/Takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY
```

**Slower Import (to avoid rate limiting):**
```bash
python google-photos-import.py \
  --takeout-dir ~/Downloads/Takeout \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY \
  --delay 1.0  # 1 second between uploads
```

### Features

✅ **Metadata Preservation**
- Original capture dates from Google Photos metadata
- GPS coordinates (latitude/longitude)
- Photo descriptions

✅ **Progress Tracking**
- Saves progress to `import-progress.json`
- Resume from where you left off if interrupted
- Real-time progress bar with stats

✅ **Duplicate Detection**
- Automatically skips photos already uploaded
- Safe to run multiple times
- Tracks duplicates in stats

✅ **Error Handling**
- Detailed logging to `google-photos-import.log`
- Continues on errors (doesn't crash)
- Reports errors in final summary

✅ **Supported Formats**
- Images: JPG, PNG, GIF, WebP, TIFF, HEIC, HEIF
- Videos: MP4, MOV, AVI, MKV, WebM, 3GP

### Google Takeout Structure

The script automatically finds your photos in the Takeout archive:

```
Takeout/
  └── Google Photos/
      ├── Photos from 2020/
      │   ├── IMG_1234.jpg
      │   ├── IMG_1234.jpg.json  <- Metadata
      │   └── ...
      ├── Photos from 2021/
      └── Albums/
          └── Vacation 2023/
              ├── photo1.jpg
              ├── photo1.jpg.json
              └── ...
```

### Progress File

`import-progress.json` contains list of uploaded files:
```json
[
  "Google Photos/Photos from 2020/IMG_1234.jpg",
  "Google Photos/Photos from 2020/IMG_5678.jpg",
  ...
]
```

Delete this file to start fresh (will re-upload everything).

### Troubleshooting

**"Could not find Google Photos directory"**
- Ensure you extracted the Takeout ZIP file
- Check that `Google Photos` folder exists in Takeout
- Try using the full path to Takeout directory

**"Upload failed (401)"**
- API key is invalid or expired
- Generate new API key in Immich settings

**"Upload failed (413)"**
- File too large for server
- Check Immich server upload limits
- May need to adjust nginx/reverse proxy settings

**Import very slow**
- Increase `--delay` to avoid overwhelming server
- Check network speed
- Large libraries take hours - this is normal!

**Some photos missing metadata**
- Google Takeout doesn't always include metadata
- Photos will still be uploaded with file timestamps
- Original capture date used when available

### Performance Tips

**For Large Libraries (10,000+ photos):**
1. Use `--batch-size 50` for more frequent progress saves
2. Use `--delay 0.5` to reduce server load
3. Run during off-hours to avoid network congestion
4. Expect several hours for completion

**For Small Libraries (<1,000 photos):**
1. Default settings work fine
2. Should complete in minutes

### Common Issues

**Duplicates after import:**
- Immich's duplicate detection may not catch all Google Photos duplicates
- Use Photo Curator's Duplicate Manager after import
- Review and clean up duplicates manually

**Wrong dates on some photos:**
- Google Takeout metadata may be incomplete
- Photos without metadata use file modification time
- You can update dates manually in Immich after import

**Albums not preserved:**
- Album structure is currently not imported (photos only)
- TODO: Add album import in future version
- Create albums manually in Immich after import

---

## Apple Photos Import

Import photos exported from the **Photos.app on macOS** to Immich, preserving EXIF metadata (capture dates, GPS).

### How to Export from Photos.app

1. Open **Photos.app** on macOS
2. Select all photos (`Cmd+A`) or a specific album
3. **File → Export → Export Unmodified Originals**
4. Choose a destination folder
5. Run this script pointing at that folder

### Usage

```bash
python apple-photos-import.py \
  --photos-dir ~/Desktop/ApplePhotosExport \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY
```

**Include Live Photo companion videos** (skipped by default):
```bash
python apple-photos-import.py \
  --photos-dir ~/Desktop/ApplePhotosExport \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY \
  --include-live-videos
```

**Resume an interrupted import** — just re-run the same command. Progress is saved in `apple-import-progress.json`.

### Features

✅ **EXIF Metadata** — Reads capture date and GPS from JPEG/PNG/HEIC files (requires Pillow)
✅ **HEIC Support** — Uploads Apple's native HEIC/HEIF format
✅ **Live Photo handling** — Companion `.MOV` files are detected and skipped by default
✅ **Progress tracking** — Resumable via `apple-import-progress.json`
✅ **Duplicate detection** — Skips already-uploaded files

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--photos-dir` | required | Path to Apple Photos export folder |
| `--immich-url` | required | Immich server URL |
| `--api-key` | required | Immich API key |
| `--include-live-videos` | off | Upload `.MOV` companion of Live Photos |
| `--batch-size` | 100 | Progress save interval (files) |
| `--delay` | 0.1 | Seconds between uploads |

---

## iCloud Photos Import

Import photos from an **Apple data export** (requested via [privacy.apple.com](https://privacy.apple.com)).

### How to Get Your iCloud Export

1. Go to **https://privacy.apple.com** and sign in with your Apple ID
2. Click **"Request a copy of your data"**
3. Select **"iCloud Photos"**
4. Choose maximum file size and submit the request
5. Apple emails a download link within **1–7 days** (large libraries take longer)
6. Download all parts and extract the ZIP file(s)

### Usage

```bash
python icloud-import.py \
  --export-dir ~/Downloads/Apple_Media_Services \
  --immich-url http://localhost:2283 \
  --api-key YOUR_API_KEY
```

**Resume an interrupted import** — just re-run the same command. Progress is saved in `icloud-import-progress.json`.

### Typical Export Structure

```
Apple_Media_Services/
  iCloud Photos/
    Photos/
      2020/
        IMG_1234.HEIC
        IMG_5678.HEIC
      2021/
        ...
```

The script auto-detects the photos directory within the export. If it can't find it, it falls back to scanning the entire export folder.

### Features

✅ **EXIF Metadata** — Reads capture date and GPS from files (requires Pillow)
✅ **Directory date fallback** — Infers year/month from folder names (e.g., `2023/`, `2023-06/`) when EXIF is absent
✅ **HEIC Support** — Uploads Apple's native HEIC/HEIF format
✅ **Auto-detection** — Finds the photos folder inside the Apple export automatically
✅ **Progress tracking** — Resumable via `icloud-import-progress.json`
✅ **Duplicate detection** — Skips already-uploaded files

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--export-dir` | required | Path to extracted Apple data export |
| `--immich-url` | required | Immich server URL |
| `--api-key` | required | Immich API key |
| `--batch-size` | 100 | Progress save interval (files) |
| `--delay` | 0.1 | Seconds between uploads |

---

## Future Migration Tools

### Planned Importers

- [ ] **Amazon Photos** - Import from Amazon Photos export
- [ ] **Facebook Photos** - Import from Facebook export
- [ ] **Flickr** - Import via Flickr API
- [ ] **Local Directory** - Bulk import from file system

### Album Import

Currently, only photos are imported (not album structure).

**Workaround:**
1. Import all photos first
2. Note album structure from Google Photos/Takeout
3. Manually recreate albums in Immich
4. Use Immich search to find photos by date/location
5. Add to recreated albums

**Future:** Album import automation planned.

## Contributing

Want to add an importer for another service?

1. Copy `google-photos-import.py` as template
2. Implement service-specific metadata extraction
3. Test with your own data
4. Submit pull request!

## API Reference

**Immich Upload API:**
```
POST /api/asset/upload
Headers:
  x-api-key: YOUR_API_KEY
Form Data:
  assetData: <file>
  deviceAssetId: <unique-id>
  deviceId: <device-name>
  fileCreatedAt: <ISO-8601-datetime>
  fileModifiedAt: <ISO-8601-datetime>
  latitude: <optional>
  longitude: <optional>
```

See: https://immich.app/docs/api/upload-asset

---

*For questions or issues, check SETUP.md or create an issue on GitHub.*
