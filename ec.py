from typing import Mapping, Any

# Reduction factors from EN 1993-1-2 / EN 1992-1-2 tables
FACTORS: dict[str, dict[str, list[float]]] = {
    "EC3": {
        # temperature break-points above the reference temperature (°C)
        # 0–80 °C is handled separately, then 100 °C steps
        "T":  [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200],
        "Fy": [1.0, 1.0, 1.0, 1.0, 0.78, 0.47, 0.23, 0.11, 0.06, 0.04, 0.02, 0.0],
        "Fp": [1.0, 0.807, 0.613, 0.420, 0.36, 0.18, 0.075, 0.050, 0.0375, 0.025, 0.0125, 0.0],
        "E":  [1.0, 0.9,  0.8,  0.7,  0.6,  0.31, 0.13, 0.09, 0.0675, 0.045, 0.0225, 0.0],
    },

    # "EC3":  (                                  # EC3 structural steel (0,3)
    #     [1.0, 1.0, 1.0, 1.0, 0.78, 0.47, 0.23, 0.11, 0.06, 0.04, 0.02, 0.0],
    #     [1.0, 0.807, 0.613, 0.420, 0.36, 0.18, 0.075, 0.050, 0.0375, 0.025, 0.0125, 0.0],
    #     [1.0, 0.9,  0.8,   0.7,  0.6,  0.31, 0.13, 0.09, 0.0675, 0.045, 0.0225, 0.0],
    # ),
    # "EC2NH": (                                 # EC2 reinforcing steel N hot-rolled (21)
    #     [1.0, 1.0, 1.0, 1.0, 0.78, 0.47, 0.23, 0.11, 0.06, 0.04, 0.02, 0.0],
    #     [1.0, 0.81, 0.61, 0.42, 0.36, 0.18, 0.07, 0.05, 0.04, 0.02, 0.01, 0.0],
    #     [1.0, 0.9,  0.8,  0.7,  0.6,  0.31, 0.13, 0.09, 0.07,  0.04, 0.02,  0.0],
    # ),
    # "EC2NC": (                                 # EC2 reinforcing steel N cold-formed (22)
    #     [1.0, 1.0, 1.0, 0.94, 0.67, 0.40, 0.12, 0.11, 0.08, 0.05, 0.03, 0.0],
    #     [0.96, 0.92, 0.81, 0.63, 0.44, 0.26, 0.08, 0.06, 0.05, 0.03, 0.02, 0.0],
    #     [1.0, 0.87, 0.72, 0.56, 0.40, 0.24, 0.08, 0.06, 0.05, 0.03, 0.02, 0.0],
    # ),
    # "EC2X": (                                  # EC2 reinforcing steel X (23)
    #     [1.0, 1.0 , 1.0 , 0.90, 0.70, 0.47, 0.23, 0.11, 0.06, 0.04, 0.02, 0.0],
    #     [1.0, 0.87, 0.74, 0.70, 0.51, 0.18, 0.07, 0.05, 0.04, 0.02, 0.01, 0.0],
    #     [1.0, 0.95, 0.90, 0.75, 0.60, 0.31, 0.13, 0.09, 0.07, 0.04, 0.02, 0.0],
    # ),
}


def _thermal_elongation(temp_abs: float) -> float:
    """
    Return thermal elongation strain ε_th (dimensionless) for steel at
    absolute temperature *temp_abs* in °C (assumes γ = 1).

    EN 1993-1-2 Annex C
    """
    if temp_abs <= 20.0:
        return 0.0
    if temp_abs <= 750.0:
        return -2.416e-4 + 1.2e-5 * temp_abs + 0.4e-8 * temp_abs**2
    if temp_abs <= 860.0:
        return 0.011
    if temp_abs <= 1200.0:
        return -6.2e-3 + 2e-5 * temp_abs
    raise ValueError("Temperature above 1200 °C is outside model range.")



def thermal_update(
    delta_temp: float,
    base_props: Mapping[str, float],
    model: str,
    *,
    reference_temperature: float = 20.0,
) -> dict[str, float]:
    """
    Parameters
    ----------
    delta_temp : float
        Temperature change with respect to *reference_temperature* (°C).
        Example: actual T = 100 °C, reference = 20 °C  →  `delta_temp = 80`.
    base_props : dict
        Material properties at *reference_temperature*.
        At minimum, supply keys that you wish to update, e.g.
        `{"E": 210e3, "Fy": 500.0}` (units are up to you).
    model : str
        Reduction-factor table to use – e.g. `"EC3"`, `"EC21"`, …
    reference_temperature : float, default 20
        Base temperature used for the tabulated factors.

    Returns
    -------
    dict
        Updated properties (same keys as *base_props*) plus
        `"elong"` → thermal elongation strain ε_th.

    Notes
    -----
    * 0–80 °C above the reference is interpolated linearly between 1.0
      and the first tabulated reduction factor (at 100 °C).
    * For 80–180 °C, 180–280 °C, … linear interpolation is performed
      between successive table entries.
    """
    if model not in FACTORS:
        raise ValueError(f"Unknown model '{model}'. Available: {list(FACTORS)}")

    factors = FACTORS[model]
    required_keys = set(base_props) & {"E", "Fy", "Fp"}  # we only know tables for these
    missing_tables = required_keys - set(factors)
    if missing_tables:
        raise ValueError(
            f"Reduction factors for {missing_tables} not available in model '{model}'."
        )

    # ................................ actual temperature ............................
    T_abs = reference_temperature + delta_temp       # absolute temperature (°C)
    if T_abs < reference_temperature or T_abs > 1200.0:
        raise ValueError("Temperature must lie within reference–1200 °C range.")

    # ................................ helper: reduction @ T .........................
    def _interp(table: list[float]) -> float:
        # Segment 0: 0–80 °C  (linear from 1.0 → table[0])
        if delta_temp <= 80.0:
            r0 = 1.0
            r1 = table[0]
            return r0 - (delta_temp / 80.0) * (r0 - r1)

        # Remaining segments: 100 °C wide
        # Convert to index in tabulated break-points
        seg = int((delta_temp - 80.0) // 100)           # 0-based
        if seg >= len(table) - 1:
            return table[-1]                            # ≥ last break-point
        r_low = table[seg]
        r_high = table[seg + 1]
        t_low = 80.0 + 100.0 * seg
        xi = (delta_temp - t_low) / 100.0               # 0–1 within segment
        return r_low - xi * (r_low - r_high)

    # ........................... assemble updated properties .......................
    out: dict[str, float] = {}
    for key, base_val in base_props.items():
        if key in factors:                             # has reduction factors
            out[key] = base_val * _interp(factors[key])
        else:                                          # no temperature dependence
            out[key] = base_val

    out["initial_strain"] = -_thermal_elongation(T_abs)/100
    return out


class EN1993:
    def __init__(self, model, code):
        """
        materials is a list of integer material tags to update
        """
        self._model = model
        self._code = code


        self._tags = {
            "Fy": 1,
            "E":  2,
            "initial_strain": 3,
            "eps0_11": 4
        }
        for pkey, ptag in self._tags.items():
            self._model.parameter(ptag)


    def init(self, temperature=20, **values):

        self._reference = values

        for tag in self._model.getEleTags(),:
            for pkey, ptag in self._tags.items():
                self._model.addToParameter(ptag, "element", tag, "allSections", pkey)

        for pkey in "Fy", "E":
            self._model.updateParameter(self._tags[pkey], values[pkey])


    def update(self, temperature):

        m = thermal_update(temperature-20, self._reference, self._code)
        m["eps0_11"] = m["initial_strain"]

        for pkey, ptag in self._tags.items():
            self._model.updateParameter(ptag, m[pkey])

