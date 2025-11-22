# Migration Tools

Tools for importing photos from various services into Immich.

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

## Future Migration Tools

### Planned Importers

- [ ] **Amazon Photos** - Import from Amazon Photos export
- [ ] **iCloud Photos** - Import from iCloud download
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
