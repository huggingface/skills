---
name: iparq-parquet-inspector
description: Inspect local or downloaded Parquet file metadata with the iParq CLI, including compression, encodings, physical and logical types, row groups, statistics, dictionary pages, page indexes, Bloom filters, and storage sizes. Use when an agent needs to explain how Parquet files or Hugging Face dataset shards were written, compare storage-level features, diagnose missing Parquet optimizations, or obtain machine-readable metadata without reading row data.
---

# iParq Parquet Inspector

Inspect Parquet storage metadata locally without querying or uploading the file's row data. Prefer JSON output so results remain machine-readable and diagnostics stay separate on stderr.

## Inspect a local file

Use the published package without installing it permanently:

```sh
uvx --refresh iparq inspect FILE.parquet --format json --details --sizes
```

If `iparq` is already installed, run it directly:

```sh
iparq inspect FILE.parquet --format json --details --sizes
```

Pass multiple paths or shell-expanded glob patterns to compare files. iParq emits one JSON object for a single file and an array with a `file` field for multiple files.

## Inspect a Hugging Face dataset shard

First locate the exact Parquet shard in the dataset repository, then download it locally. For example:

```sh
hf download OWNER/DATASET PATH/TO/SHARD.parquet \
  --repo-type dataset \
  --local-dir ./hf-dataset

uvx --refresh iparq inspect ./hf-dataset/PATH/TO/SHARD.parquet \
  --format json --details --sizes
```

For gated or private datasets, authenticate with `hf auth login` before downloading. Do not upload a user's Parquet file to inspect it; iParq is intended to run where the file is stored.

## Select the minimum useful detail

- Use `--metadata-only` for creator, row count, row groups, Parquet version, and serialized metadata size.
- Use `--column NAME` to restrict column-level output.
- Use `--details` for encodings, physical and logical types, dictionary pages, page indexes, Bloom-filter metadata, and detailed statistics.
- Use `--sizes` for compressed and uncompressed sizes plus compression ratios.
- Keep `--format json` for agent workflows. Use the default Rich output only when a human explicitly wants a table.

## Interpret results

Report observed facts separately from recommendations. In particular:

- Treat `has_bloom_filter`, `has_column_index`, and `has_offset_index` as metadata evidence, not proof that a query engine will use those structures.
- Compare compression ratios in the context of data type, cardinality, encoding, and row-group layout.
- Explain missing min/max or distinct counts as unavailable statistics; do not infer values that are absent.
- Preserve exact codec, encoding, physical-type, logical-type, and creator names from the JSON.
- Mention the affected file and column when comparing multiple inputs.

## Handle failures safely

Do not modify the inspected files. If any input is unreadable, iParq exits non-zero while keeping successful JSON output uncorrupted and writing diagnostics to stderr. Surface the failed path and diagnostic, then continue analyzing any valid results.

## Project links

- Documentation: https://iparq.dev/docs/
- Source: https://github.com/MiguelElGallo/iparq
- PyPI: https://pypi.org/project/iparq/
