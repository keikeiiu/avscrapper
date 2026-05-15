# Folder Reorganizer

Moves processed folders into a customizable metadata-driven hierarchy.

## Config

Add to `config.yaml`:

```yaml
reorganize:
  target: "C:/Users/keiwa/Downloads/reorganized_"
  fc2_template: "{seller}/{premiered:4}/FC2-PPV-{cid}"
  jav_template: "{studio}/{series}/{cid}"
```

## Template Variables

| Variable | Source | Example |
|----------|--------|---------|
| `{cid}` | DB cid | 409694, ABP-948 |
| `{title}` | DB title | 密着ドキュメント |
| `{seller}` | FC2 seller | 六本木円光神話 |
| `{studio}` | JAV studio / maker | S1 NO.1 STYLE |
| `{label}` | JAV label | S1 NO.1 STYLE |
| `{series}` | JAV series | 台本一切無し！！ |
| `{director}` | JAV director | 嵐山みちる |
| `{premiered}` | release_date (YYYY-MM-DD) | 2021-07-19 |
| `{premiered:N}` | first N chars | `{premiered:4}` → 2021 |
| `{year}` | year only | 2021 |
| `{actress}` | first actress name | 架乃ゆら |
| `{rating}` | user rating | 4.16 |

## Template Examples

```yaml
# FC2 — By seller then year
fc2_template: "{seller}/{premiered:4}/FC2-PPV-{cid}"

# FC2 — Flat with title
fc2_template: "FC2-PPV-{cid} - {title}"

# JAV — Studio → Series → ID
jav_template: "{studio}/{series}/{cid}"

# JAV — Director-focused
jav_template: "{director}/{premiered:4}/{cid}"

# JAV — Studio → Actress → ID
jav_template: "{studio}/{actress}/{cid}"
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
