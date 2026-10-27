# Synthetic detector demonstration: methods and limitations

This demonstration uses **simulated measurements only**. It does not reconstruct
the laboratory source collection or alter the published results. Its CSV schemas
are a small public example, not verified replicas of the instrument export formats.
The existing `prepare_data.py` remains the processor for authentic exports.

## Run the pipeline

Python 3.9 or later, standard library only:

```bash
python3 scripts/run_demo.py
python3 -m unittest discover -s tests -v
```

The default output is `demo_output/` relative to the repository, regardless of the
working directory. It contains `pedestal.csv`, `calibration.csv`, `manifest.json`,
`qc_report.json`, and `qc_report.md`. It is ignored by Git. The manifest records
simulation parameters, the seed, schema version, synthetic label and SHA-256 input
checksums. Reports record the input and manifest checksums and QC thresholds.
Repeat runs replace only the known demo files, and refuse directories containing
unrelated files, symlinks, or a missing/non-synthetic demo marker.

To generate inputs separately and inspect them before analysis:

```bash
python3 scripts/generate_synthetic.py --seed 42
python3 scripts/scientific_qc.py --max-noise-adc 3 --max-residual-rms-adc 2 --min-r-squared 0.99
```

Both commands accept a directory (`--output` for generation; `--input` for QC).
`run_demo.py` accepts `--output`, `--seed`, and all three threshold flags. Fixed
seeds reproduce files in the same Python runtime. Different seeds give different
statistical samples; the observed noise is not hard-coded to a previous report.

## Simulated measurements

There are 32 zero-based channels (0–31). Each has 256 independent pedestal events,
drawn from a Gaussian with mean `100 + 0.2 * channel` ADC and sigma 1.2 ADC.
Channel 31 deliberately uses sigma 6 ADC to demonstrate an elevated-noise warning.
Noise is the sample standard deviation (denominator N−1). This is uncorrected
pedestal noise; it must not be equated with the authentic common-mode-corrected
noise table.

Each channel has four independent calibration repeats at 0, 2, 4, 6, 8 and 10 fC.
The model is `ADC = 100 + 0.2 * channel + (7 + 0.03 * channel) * charge_fc + error`,
with Gaussian ADC error sigma 0.65. Charge is treated as exact. There is no
clipping, saturation, cross-talk, common-mode noise, drift, source spectrum or
laser scan model in this milestone.

## Calibration and uncertainty

`fit_calibration.py` fits all individual repeated measurements by unweighted
ordinary least squares: `ADC = a + b * charge_fc`. It reports intercept `a`, gain
`b` (ADC/fC), residual RMS, R squared, degrees of freedom and parameter standard
errors. With N points, Sxx = Σ(x−mean(x))², and SSE = Σ(y−a−bx)²:

- Residual RMS = sqrt(SSE/N).
- Estimated residual variance s² = SSE/(N−2).
- SE(b) = sqrt(s²/Sxx).
- SE(a) = sqrt(s² * (1/N + mean(x)²/Sxx)).

These are one-standard-error estimates conditional on a linear response,
independent homoscedastic ADC errors, and negligible injected-charge uncertainty.
They exclude systematic uncertainty and do not imply a validated detector model.
R squared is undefined for constant ADC response and is reported as JSON `null`.
Charge-to-energy equivalence does not establish a validated inverse ADC-to-energy
calibration. No particle energy inference is performed.

## Integrity versus scientific quality

Before fitting, the QC reader requires an explicit synthetic marker and schema
version, verifies both input checksums, validates columns and finite values, and
checks complete channel/event/charge/repeat coverage without duplicates. Invalid
or incomplete data stop analysis with exit code 2 rather than appearing as a
scientifically acceptable report.

For valid inputs, channel rules are:

| Rule | Default criterion | Status when breached |
| --- | --- | --- |
| Pedestal noise | Sample SD ≤ 3 ADC | warning |
| Calibration residual | RMS ≤ 2 ADC | warning |
| Linear response | R squared ≥ 0.99 | warning (also if undefined) |
| Positive gain | Gain > 0 ADC/fC | failure |

Thresholds are illustrative, not acceptance criteria established for a physical
detector. Reports explain every check and use the most severe channel status as
the overall status. Counts refer to channels, not the number of triggered rules.
The fixed-seed default should flag channel 31 alone. A warning returns exit code 0
so the deliberate anomaly can be demonstrated in CI; a scientific failure returns
1, and invalid input or configuration returns 2.

## Scope

This milestone provides synthetic inputs, calibration metrics, integrity checks,
scientific QC, JSON/Markdown reports and unit tests. HTML reporting, calibration
and residual plots, cluster/scan QC, and an interactive dashboard are future work.
Use the established workflow and preservation tools for authentic laboratory data;
the synthetic manifest is separate from the authentic provenance manifests.
