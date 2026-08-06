# Troubleshooting

## E001: `SKILL_FILE_NOT_FOUND`

Cause: The path passed to `--input_file` does not exist.

Fix:

```bash
ls -l your_input_file.csv
```

Use an absolute path if you are unsure about the working directory.

## E002: `SKILL_MISSING_COLUMNS`

Cause: One or more names in `--columns` do not exist in the input header.

Fix:

1. Open the first row of the input file.
2. Copy the exact column names.
3. Pass them in the desired order, for example `--columns risk,Responder,Subtype`.

## E003: `SKILL_EMPTY_DATA`

Cause: The input file has no rows, or fewer than two usable stage columns are available.

Fix:

1. Ensure the file contains data rows under the header.
2. Provide at least two stage columns.
3. If you use `--columns`, confirm that at least two names are listed.

## E004: `SKILL_INVALID_PARAMETER`

Cause: A numeric CLI value is invalid.

Examples:

- `--width <= 0`
- `--height <= 0`
- `--alpha < 0` or `--alpha > 1`
- `--label_size <= 0`

Fix: Re-run the command with valid numeric values.

## E005: `SKILL_DEPENDENCY_MISSING`

Cause: Required R packages are not installed.

Fix:

```bash
Rscript scripts/install_dependencies.R
```

This command installs any missing CRAN packages required by the skill and tests.

Or install manually:

```bash
Rscript -e "install.packages(c('optparse','ggplot2','ggalluvial','testthat'), repos='https://cloud.r-project.org')"
```

## E006: `SKILL_IO_ERROR`

Cause: The output directory could not be created or written.

Fix:

1. Check that the parent directory exists.
2. Confirm you have write permission.
3. Re-run with a different `--output_dir` if needed.

## Plot Labels Overlap

Cause: Too many strata are plotted at once.

Fix:

1. Reduce the number of columns in `--columns`.
2. Increase `--width` or `--height`.
3. Lower `--label_size`.

## Output Uses the Label `Missing`

Cause: Empty strings or `NA` values were found in selected stage columns.

Fix:

1. Clean the input table upstream if missing labels are unexpected.
2. Or replace the label with `--missing_label Unknown`.
