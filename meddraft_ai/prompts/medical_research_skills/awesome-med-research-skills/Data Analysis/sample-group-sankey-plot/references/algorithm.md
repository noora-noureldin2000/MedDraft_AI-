# Algorithm Notes

## Purpose

This skill converts a sample annotation table into a Sankey/alluvial plot. Each row is treated as one sample trajectory and each selected column is treated as one categorical stage.

## Data Transformation

1. Read the annotation table from CSV or TSV.
2. Select the requested stage columns in the user-provided order.
3. Replace blank and `NA` values with a stable missing-value label.
4. Create a synthetic `sample_id` for each row so each sample can be tracked across stages.
5. Use `ggalluvial::to_lodes_form()` to transform the wide annotation table into lodes format.

The transformed lodes table has one row per sample-stage combination.

## Plot Construction

- `geom_flow()` draws the transitions between adjacent stages.
- `geom_stratum()` draws one rectangle per category at each stage.
- `geom_text(stat = "stratum")` labels each stratum directly.
- `theme_void()` removes axes and gridlines because the categorical stage order is encoded on the x-axis.

## Assumptions

- Input columns are categorical or can be safely coerced to character labels.
- The order of `--columns` is meaningful and defines the left-to-right stage order.
- Each row is one independent sample pathway.

## Relationship to the Original Script

The original `基因-桑葚图.R` script manually selected `risk` and `Responder` columns from an in-memory object and plotted them directly. The converted skill preserves that behavior but generalizes it to external files and arbitrary stage columns.
