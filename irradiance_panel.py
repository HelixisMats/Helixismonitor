"""Sun geometry and a clear-sky reference, written out rather than imported.

pvlib would give all of this and more, but it is one more package that has to
install cleanly on the server, and this app has already lost an afternoon to a
dependency that did not travel. Forty lines of NOAA and Ineichen have no
install step.
"""
import numpy as np
import pandas as pd


def solar_position(times_utc, lat, lon):
    """Solar elevation and zenith in degrees. NOAA's low-precision algorithm,
    good to about 0.1° — far below the other errors in this comparison."""
    t = pd.DatetimeIndex(times_utc)
    doy = t.dayofyear.values.astype(float)
    hour = (t.hour.values + t.minute.values / 60.0 + t.second.values / 3600.0)

    gamma = 2 * np.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    eqtime = 229.18 * (0.000075
                       + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                       - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
    decl = (0.006918
            - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma)
            - 0.006758 * np.cos(2 * gamma) + 0.000907 * np.sin(2 * gamma)
            - 0.002697 * np.cos(3 * gamma) + 0.001480 * np.sin(3 * gamma))

    time_offset = eqtime + 4.0 * lon                 # minutes, times are UTC
    tst = hour * 60.0 + time_offset
    ha = np.radians(tst / 4.0 - 180.0)

    latr = np.radians(lat)
    cosz = (np.sin(latr) * np.sin(decl)
            + np.cos(latr) * np.cos(decl) * np.cos(ha))
    cosz = np.clip(cosz, -1.0, 1.0)
    zenith = np.degrees(np.arccos(cosz))
    return pd.DataFrame({"zenith": zenith, "elevation": 90.0 - zenith}, index=t)


def clear_sky(times_utc, lat, lon, altitude=100.0, linke=3.0):
    """Ineichen–Perez clear-sky GHI and DNI, W/m².

    linke is the Linke turbidity: 2.5–3 is a clean Nordic winter sky, 4–5 a
    hazy summer one. It is the one knob worth turning if the envelope sits
    consistently above or below the clearest measured days."""
    pos = solar_position(times_utc, lat, lon)
    z = np.radians(pos["zenith"].values)
    zdeg = pos["zenith"].values
    cosz = np.cos(z)

    doy = pd.DatetimeIndex(times_utc).dayofyear.values.astype(float)
    i0 = 1367.0 * (1 + 0.033 * np.cos(2 * np.pi * doy / 365.0))

    with np.errstate(invalid="ignore", divide="ignore"):
        am = 1.0 / (cosz + 0.50572 * np.power(96.07995 - zdeg, -1.6364))
    am = np.where(zdeg < 90, am, np.nan)

    fh1 = np.exp(-altitude / 8000.0)
    fh2 = np.exp(-altitude / 1250.0)
    cg1 = 5.09e-5 * altitude + 0.868
    cg2 = 3.92e-5 * altitude + 0.0387

    ghi = (cg1 * i0 * cosz
           * np.exp(-cg2 * am * (fh1 + fh2 * (linke - 1)))
           * np.exp(0.01 * np.power(am, 1.8)))
    b = 0.664 + 0.163 / fh1
    dni = b * i0 * np.exp(-0.09 * am * (linke - 1))

    ghi = np.where((zdeg < 90) & np.isfinite(ghi), np.maximum(ghi, 0.0), 0.0)
    dni = np.where((zdeg < 90) & np.isfinite(dni), np.clip(dni, 0.0, i0), 0.0)
    return pd.DataFrame({"ghi_clear": ghi, "dni_clear": dni,
                         "elevation": pos["elevation"].values},
                        index=pd.DatetimeIndex(times_utc))


def fit_line(x, y):
    """Least squares y = a·x + b, plus Pearson r. Returns (a, b, r, n)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3 or x.std() == 0:
        return None, None, None, len(x)
    a, b = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return float(a), float(b), r, len(x)
