# CLI Usage Guide

## Basic Syntax

```bash
Rscript scripts/main.R [OPTIONS]
```

## Required Arguments

| Argument | Description |
|----------|-------------|
| `-i FILE` | Annotation table file (CSV/TSV) |

## Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `-o DIR` | ./output/ | Output directory |
| `-c COLUMNS` | all columns | Comma-separated stage columns to plot |
| `-p PREFIX` | sankey_plot | Output file prefix |
| `--width VALUE` | 7 | Plot width in inches |
| `--height VALUE` | 5 | Plot height in inches |
| `--alpha VALUE` | 0.5 | Flow transparency between 0 and 1 |
| `--label_size VALUE` | 4.5 | Stratum label size |
| `--missing_label TEXT` | Missing | Replacement label for blank or NA values |
| `--title TEXT` | empty | Optional plot title |
| `-s VALUE` | 42 | Random seed |
| `--timeout VALUE` | 3600 | Maximum elapsed runtime in seconds; use `0` to disable |

## Complete Examples

### Example 1: Minimal Sankey Plot

```bash
Rscript scripts/main.R \
  -i tests/data/sample_annotations.csv \
  -o results \
  -c risk,Responder
```

### Output Files

| File | Size (bytes) |
|------|--------------|
| `data/session_info.txt` | `1709` |
| `plot/sankey_plot.pdf` | `6366` |
| `table/sankey_lodes.csv` | `236` |
| `table/selected_annotations.csv` | `91` |

### Runtime and Resource Usage

| Metric | Value |
|--------|-------|
| Start time | `2026-04-16 17:14:32` |
| End time | `2026-04-16 17:14:33` |
| Exit code | `0` |
| Wall-clock time | `1.078` |
| User CPU time | `1.169` |
| System CPU time | `1.218` |
| Max resident set size | `Not recorded` |

### Example 2: Include More Stages

```bash
Rscript scripts/main.R \
  -i tests/data/sample_annotations.csv \
  -o results \
  -c risk,Responder,Subtype
```

### Output Files

| File | Size (bytes) |
|------|--------------|
| `data/session_info.txt` | `1717` |
| `plot/sankey_plot.pdf` | `9038` |
| `table/sankey_lodes.csv` | `352` |
| `table/selected_annotations.csv` | `145` |

### Runtime and Resource Usage

| Metric | Value |
|--------|-------|
| Start time | `2026-04-16 17:14:59` |
| End time | `2026-04-16 17:15:00` |
| Exit code | `0` |
| Wall-clock time | `1.165` |
| User CPU time | `1.280` |
| System CPU time | `1.319` |
| Max resident set size | `Not recorded` |

### Example 3: Adjust Plot Appearance

```bash
Rscript scripts/main.R \
  -i tests/data/sample_annotations.csv \
  -o results \
  -c risk,Responder,Subtype \
  --width 9 \
  --height 6 \
  --alpha 0.65 \
  --label_size 3.8 \
  --title "Sample transition map"
```

### Output Files

| File | Size (bytes) |
|------|--------------|
| `data/session_info.txt` | `1739` |
| `plot/sankey_plot.pdf` | `9132` |
| `table/sankey_lodes.csv` | `352` |
| `table/selected_annotations.csv` | `145` |

### Runtime and Resource Usage

| Metric | Value |
|--------|-------|
| Start time | `2026-04-16 17:15:30` |
| End time | `2026-04-16 17:15:32` |
| Exit code | `0` |
| Wall-clock time | `1.558` |
| User CPU time | `1.168` |
| System CPU time | `1.337` |
| Max resident set size | `Not recorded` |

### Example 4: Bound Runtime

```bash
Rscript scripts/main.R \
  -i tests/data/sample_annotations.csv \
  -o results \
  -c risk,Responder,Subtype \
  --timeout 600
```

### Output Files

| File | Size (bytes) |
|------|--------------|
| `data/session_info.txt` | `1717` |
| `plot/sankey_plot.pdf` | `9038` |
| `table/sankey_lodes.csv` | `352` |
| `table/selected_annotations.csv` | `145` |

### Runtime and Resource Usage

| Metric | Value |
|--------|-------|
| Start time | `2026-04-16 17:16:27` |
| End time | `2026-04-16 17:16:28` |
| Exit code | `0` |
| Wall-clock time | `1.137` |
| User CPU time | `1.189` |
| System CPU time | `1.259` |
| Max resident set size | `Not recorded` |

### Example 5: Use All Columns Automatically

```bash
Rscript scripts/main.R \
  -i tests/data/sample_annotations.csv \
  -o results
```

### Output Files

| File | Size (bytes) |
|------|--------------|
| `data/session_info.txt` | `1726` |
| `plot/sankey_plot.pdf` | `11997` |
| `table/sankey_lodes.csv` | `460` |
| `table/selected_annotations.csv` | `186` |

### Runtime and Resource Usage

| Metric | Value |
|--------|-------|
| Start time | `2026-04-16 17:19:43` |
| End time | `2026-04-16 17:19:44` |
| Exit code | `0` |
| Wall-clock time | `1.164` |
| User CPU time | `1.240` |
| System CPU time | `1.247` |
| Max resident set size | `Not recorded` |


## Getting Help

```bash
Rscript scripts/main.R --help
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (file not found, invalid parameter, missing package, etc.) |
