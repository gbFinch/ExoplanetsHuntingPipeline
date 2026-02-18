# Exohunt

Tools for fetching and inspecting TESS light curves.

## Quickstart

```bash
source .venv/bin/activate
pip install -e .[dev]
python -m exohunt.cli --target "TIC 261136679"
```

By default, downloaded stitched light curves are cached under `outputs/cache/lightcurves`.
Prepared (preprocessed) light curves are also cached there using preprocessing-parameter keys,
so repeated runs with the same settings skip flattening.
Use `--refresh-cache` to ignore cache and download fresh data:

```bash
python -m exohunt.cli --target "TIC 261136679" --refresh-cache
```

Preprocessing is now applied before plotting (normalize, outlier filtering, flattening):

```bash
python -m exohunt.cli --target "TIC 261136679" --outlier-sigma 5 --flatten-window-length 401
```

The output plot is saved as `outputs/plots/<target>_prepared.png`.
