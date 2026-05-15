# Folder Reorganizer

Moves processed folders into a customizable metadata-driven hierarchy.

## Config

Add to `config.yaml`:

```yaml
reorganize:
  target: "C:/Users/keiwa/Downloads/reorganized_"
  fc2_structure: "FC2/{seller}/{premiered:4}/{cid} - {title:50}"
  jav_structure: "JAV/{studio}/{series}/{cid}"
  studio_map:
    SODクリエイト: SOD Create
  series_map: {}
```

## Structure Variables

| Variable | Source | Example |
|----------|--------|---------|
| `{cid}` | DB cid | 409694 |
| `{title}` | DB title (sanitized) | 密着ドキュメント |
| `{title:N}` | first N chars | `{title:50}` |
| `{seller}` | FC2 seller | 六本木円光神話 |
| `{studio}` | JAV studio (after map) | S1 NO.1 STYLE |
| `{series}` | JAV series (after map) | 台本一切無し！！ |
| `{label}` | JAV label | S1 NO.1 STYLE |
| `{director}` | JAV director | 嵐山みちる |
| `{premiered}` | release_date | 2021-07-19 |
| `{premiered:N}` | first N chars | `{premiered:4}` → 2021 |
| `{year}` | year only | 2021 |
| `{actress}` | first actress | 架乃ゆら |
| `{rating}` | user rating | 4.16 |

## Structure Examples

```yaml
# FC2 — Seller → Year → ID + Title
fc2_structure: "FC2/{seller}/{premiered:4}/{cid} - {title:50}"

# JAV — Studio → Series → ID
jav_structure: "JAV/{studio}/{series}/{cid}"

# JAV — Director-focused with title
jav_structure: "JAV/{director}/{premiered:4}/{cid} - {title:40}"
```

## Studio & Series Map

Normalize inconsistent JavDB names:

```yaml
studio_map:
  SODクリエイト: SOD Create
  SODマジックミラー号: SOD Create

series_map:
  "※台本一切無し！！ハメ撮り！すっぴん！何でもアリ！ ○○のスケベ本性剥き出しSEX！！": "※台本一切無し！！"
```

## Safety

Each file is processed atomically:

```
1. Copy file to target
2. Verify file sizes match
3. Delete source file
4. Log to report
```

If interrupted: source files remain, target has partial copies. Re-run to resume — already-moved entries are skipped.

## Usage

```bash
# Preview changes
python reorganize.py --dry-run

# Execute (copy-verify-delete)
python reorganize.py

# Specific entries only
python reorganize.py --ids ABP-948,STARS-086

# Specific type only
python reorganize.py --type fc2
```

## Invalid Characters

Template values are sanitized: `: * ? " < > |` are replaced with `-`. Leading/trailing spaces and dots are trimmed.
