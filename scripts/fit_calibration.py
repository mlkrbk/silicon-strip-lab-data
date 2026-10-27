"""Ordinary least squares for ADC = intercept + gain * injected charge (fC)."""
import math
import statistics


def fit_linear(points):
    points = list(points)
    if len(points) < 3 or any(not math.isfinite(v) for point in points for v in point):
        raise ValueError('Linear fit needs at least three finite (charge, ADC) points')
    x, y = zip(*points)
    x_mean, y_mean = statistics.mean(x), statistics.mean(y)
    sxx = sum((value - x_mean) ** 2 for value in x)
    if sxx <= 0:
        raise ValueError('Linear fit needs distinct charge settings')
    gain = sum((a - x_mean) * (b - y_mean) for a, b in points) / sxx
    intercept = y_mean - gain * x_mean
    residuals = [b - (intercept + gain * a) for a, b in points]
    sse = sum(value ** 2 for value in residuals)
    variance = sse / (len(points) - 2)
    syy = sum((value - y_mean) ** 2 for value in y)
    return {
        'gain_adc_per_fc': gain, 'intercept_adc': intercept,
        'gain_standard_error_adc_per_fc': math.sqrt(variance / sxx),
        'intercept_standard_error_adc': math.sqrt(variance * (1 / len(points) + x_mean ** 2 / sxx)),
        'residual_rms_adc': math.sqrt(sse / len(points)),
        'residual_standard_error_adc': math.sqrt(variance),
        'r_squared': 1 - sse / syy if syy > 0 else None,
        'degrees_of_freedom': len(points) - 2, 'point_count': len(points),
    }
