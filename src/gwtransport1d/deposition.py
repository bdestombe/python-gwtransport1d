"""
Deposition and Concentration Analysis for Aquifer Systems.

This module provides functions to analyze compound deposition and concentration
in aquifer systems. It includes tools for computing deposition rates, concentration
changes, and related coefficients based on extraction data and aquifer properties.

The model assumes requires the groundwaterflow to be reduced to a 1D system. On one side,
water with a certain concentration infiltrates ('cin'), the water flows through the aquifer and
the compound of intrest flows through the aquifer with a retarded velocity. During the soil pasage,
deposition enriches the water with the compound. The water is extracted ('cout') and the concentration
increase due to deposition is called 'dcout'.

Main functions:
- compute_deposition: Calculate deposition rates from extraction data
- compute_dc: Determine concentration changes due to deposition
- deposition_coefficients: Generate coefficients for deposition modeling
- interp_series: Interpolate time series data to new time points

The module leverages numpy, pandas, and scipy for efficient numerical computations
and time series handling. It is designed for researchers and engineers working on
groundwater contamination and transport problems.
"""

import numpy as np
import pandas as pd
from scipy import interpolate
from scipy.linalg import null_space
from scipy.optimize import minimize

from gwtransport1d.residence_time import residence_time_retarded


def compute_deposition(
    cout, flow, aquifer_pore_volume, porosity, thickness, retardation_factor, nullspace_objective="squared_lengths"
):
    """
    Compute the deposition given the added concentration of the compound in the extracted water.

    The length of flow should already correspond to the length of cout:

    >>> start = cout.index.min() - pd.to_timedelta(
    ...     rt_extraction[cout.index.min()], "D"
    ... ).ceil("D")
    >>> end = cout.index.max()
    >>> flow = flow.resample("D", label="right").median().loc[start:end]

    Parameters
    ----------
    cout : pandas.Series
        Concentration of the compound in the extracted water [ng/m3].
    flow : pandas.Series
        Flow rate of water in the aquifer [m3/day].
    aquifer_pore_volume : float
        Pore volume of the aquifer [m3].
    porosity : float
        Porosity of the aquifer [dimensionless].
    thickness : float
        Thickness of the aquifer [m].
    retardation_factor : float
        Retardation factor of the compound in the aquifer [dimensionless].
    nullspace_objective : str or callable, optional
        Objective to minimize in the nullspace. If a string, it should be either "squared_lengths" or "summed_lengths". If a callable, it should take the form `objective(x, xLS, colsOfNullspace)`. Default is "squared_lengths".

    Returns
    -------
    pandas.Series
        Deposition of the compound in the aquifer [ng/m2/day].
    """
    # concentration extracted water is coeff dot deposition
    coeff, _, index_dep = deposition_coefficients(
        cout.index,
        flow,
        aquifer_pore_volume,
        porosity=porosity,
        thickness=thickness,
        retardation_factor=retardation_factor,
    )

    # cout should be of length coeff.shape[0]
    if len(cout) != coeff.shape[0]:
        msg = f"Length of cout ({len(cout)}) should be equal to the number of rows in coeff ({coeff.shape[0]})"
        raise ValueError(msg)

    if not index_dep.isin(flow.index).all():
        msg = "The flow timeseries is either not long enough or is not alligned well"
        raise ValueError(msg, index_dep, flow.index)

    # Underdetermined least squares solution
    deposition_ls, *_ = np.linalg.lstsq(coeff, cout, rcond=None)

    # Nullspace -> multiple solutions exist, deposition_ls is just one of them
    cols_of_nullspace = null_space(coeff, rcond=None)
    nullrank = cols_of_nullspace.shape[1]

    # Pick a solution in the nullspace that meets new objective
    def objective(x, x_ls, cols_of_nullspace):
        sols = x_ls + cols_of_nullspace @ x
        return np.square(sols[1:] - sols[:-1]).sum()

    deposition_0 = np.zeros(nullrank)
    res = minimize(objective, x0=deposition_0, args=(deposition_ls, cols_of_nullspace), method="BFGS")

    if not res.success:
        msg = f"Optimization failed: {res.message}"
        raise ValueError(msg)

    # Squared lengths is stable to solve, thus a good starting point
    if nullspace_objective != "squared_lengths":
        if nullspace_objective == "summed_lengths":

            def objective(x, x_ls, cols_of_nullspace):
                sols = x_ls + cols_of_nullspace @ x
                return np.abs(sols[1:] - sols[:-1]).sum()

            res = minimize(objective, x0=res.x, args=(deposition_ls, cols_of_nullspace), method="BFGS")

        elif callable(nullspace_objective):
            res = minimize(nullspace_objective, x0=res.x, args=(deposition_ls, cols_of_nullspace), method="BFGS")

        else:
            msg = f"Unknown nullspace objective: {nullspace_objective}"
            raise ValueError(msg)

    deposition_data = deposition_ls + cols_of_nullspace @ res.x
    return pd.Series(data=deposition_data, index=index_dep, name="deposition")


def compute_dc(dcout_index, deposition, flow, aquifer_pore_volume, porosity, thickness, retardation_factor):
    """
    Compute the increase in concentration of the compound in the extracted water by the deposition.

    Parameters
    ----------
    dcout_index : pandas.Series
        Concentration of the compound in the extracted water [ng/m3].
    deposition : pandas.Series
        Deposition of the compound in the aquifer [ng/m2/day].
    flow : pandas.Series
        Flow rate of water in the aquifer [m3/day].
    aquifer_pore_volume : float
        Pore volume of the aquifer [m3].
    porosity : float
        Porosity of the aquifer [dimensionless].
    thickness : float
        Thickness of the aquiifer [m].

    Returns
    -------
    pandas.Series
        Concentration of the compound in the extracted water [ng/m3].
    """
    cout_date_range = dcout_date_range_from_dcout_index(dcout_index)
    coeff, _, _dep_index = deposition_coefficients(
        cout_date_range,
        flow,
        aquifer_pore_volume,
        porosity=porosity,
        thickness=thickness,
        retardation_factor=retardation_factor,
    )
    # coeff_overlapping = coeff[:, index.isin(deposition.index)]  # what if coeff is smaller than deposition?
    return pd.Series(coeff @ deposition, index=dcout_index, name="dcout")


def dcout_date_range_from_dcout_index(dcout_index):
    """
    Compute the date range of the concentration of the compound in the extracted water.

    Parameters
    ----------
    dcout_index : pandas.DatetimeIndex
        Index of the concentration of the compound in the extracted water.

    Returns
    -------
    pandas.DatetimeIndex
        Date range of the concentration of the compound in the extracted water.
    """
    return pd.date_range(start=dcout_index.min().floor("D"), end=dcout_index.max(), freq="D")


def deposition_index_from_dcout_index(dcout_index, flow, aquifer_pore_volume, retardation_factor):
    """
    Compute the index of the deposition from the concentration of the compound in the extracted water index.

    Creates and index for each day, starting at the first day that contributes to the first dcout measurement,
    and ending at the last day that contributes to the last dcout measurement. The times are floored to the
    beginning of the day.

    Parameters
    ----------
    dcout_index : pandas.DatetimeIndex
        Index of the concentration of the compound in the extracted water.
    flow : pandas.Series
        Flow rate of water in the aquifer [m3/day].
    aquifer_pore_volume : float
        Pore volume of the aquifer [m3].
    retardation_factor : float
        Retardation factor of the compound in the aquifer [dimensionless].

    Returns
    -------
    pandas.DatetimeIndex
        Index of the deposition.
    """
    rt = residence_time_retarded(
        flow, aquifer_pore_volume, retardation_factor=retardation_factor, direction="extraction"
    )
    rt_at_start_cout = pd.to_timedelta(interp_series(rt, dcout_index.min()), "D")
    start_dep = (dcout_index.min() - rt_at_start_cout).floor("D")
    end_dep = dcout_index.max()
    return pd.date_range(start=start_dep, end=end_dep, freq="D")


def deposition_coefficients(dcout_index, flow, aquifer_pore_volume, porosity, thickness, retardation_factor):
    """
    Compute the coefficients of the deposition model.

    Parameters
    ----------
    dcout_index : pandas.Series
        Concentration of the compound in the extracted water [ng/m3].
    flow : pandas.Series
        Flow rate of water in the aquifer [m3/day].
    aquifer_pore_volume : float
        Pore volume of the aquifer [m3].
    porosity : float
        Porosity of the aquifer [dimensionless].
    thickness : float
        Thickness of the aquifer [m].
    retardation_factor : float
        Retardation factor of the compound in the aquifer [dimensionless].

    Returns
    -------
    numpy.ndarray
        Coefficients of the deposition model [m2/day].
    pandas.DataFrame
        Dataframe containing the residence time of the retarded compound in the aquifer [days].
    pandas.DatetimeIndex
        Datetime index of the deposition.
    """
    # Get deposition indices
    rt = residence_time_retarded(
        flow, aquifer_pore_volume, retardation_factor=retardation_factor, direction="extraction"
    )
    # rt_at_start_cout = pd.to_timedelta(interp_series(rt, dcout_index.min()), "D")
    # start_dep = (dcout_index.min() - rt_at_start_cout).floor("D")
    # end_dep = dcout_index.max()
    # index_dep = pd.date_range(start=start_dep, end=end_dep, freq="D")
    index_dep = deposition_index_from_dcout_index(dcout_index, flow, aquifer_pore_volume, retardation_factor)

    if not index_dep.isin(flow.index).all():
        msg = "The flow timeseries is either not long enough or is not alligned well"
        raise ValueError(msg, index_dep, flow.index)

    df = pd.DataFrame(
        data={
            "flow": flow[dcout_index.floor(freq="D")].values,
            "rt": pd.to_timedelta(interp_series(rt, dcout_index), "D"),
            "dates_infiltration_retarded": dcout_index - pd.to_timedelta(interp_series(rt, dcout_index), "D"),
            "darea": flow[dcout_index.floor(freq="D")].values
            / (retardation_factor * porosity * thickness),  # Aquifer area cathing deposition
        },
        index=dcout_index,
    )

    # Compute coefficients
    dt = np.zeros((len(dcout_index), len(index_dep)), dtype=float)

    for iout, (date_extraction, row) in enumerate(df.iterrows()):
        itinf = index_dep.searchsorted(row.dates_infiltration_retarded.floor(freq="D"))  # partial day
        itextr = index_dep.searchsorted(date_extraction.floor(freq="D"))  # whole day

        dt[iout, itinf] = (index_dep[itinf + 1] - row.dates_infiltration_retarded) / pd.to_timedelta(1.0, unit="D")
        dt[iout, itinf + 1 : itextr] = 1.0

        # fraction of first day
        dt[iout, itextr] = (date_extraction - index_dep[itextr]) / pd.to_timedelta(1.0, unit="D")

    if not np.isclose(dt.sum(axis=1), df.rt.values / pd.to_timedelta(1.0, unit="D")).all():
        msg = "Residence times do not match"
        raise ValueError(msg)

    flow_floor = flow.median() / 100.0  # m3/day To increase numerical stability
    flow_floored = df.flow.clip(lower=flow_floor)
    coeff = (df.darea / flow_floored).values[:, None] * dt

    if np.isnan(coeff).any():
        msg = "Coefficients contain nan values."
        raise ValueError(msg)

    return coeff, df, index_dep

def interp_series(series, index_new, **interp1d_kwargs):
    """
    Interpolate a pandas.Series to a new index.

    Parameters
    ----------
    series : pandas.Series
        Series to interpolate.
    index_new : pandas.DatetimeIndex
        New index to interpolate to.
    interp1d_kwargs : dict, optional
        Keyword arguments passed to scipy.interpolate.interp1d. Default is {}.

    Returns
    -------
    pandas.Series
        Interpolated series.
    """
    if not isinstance(series, pd.Series):
        msg = "Input should be a pandas.Series"
        raise TypeError(msg)

    if not isinstance(series.index, pd.DatetimeIndex):
        msg = "series should have a pandas.DatetimeIndex"
        raise TypeError(msg)

    if not isinstance(index_new, pd.DatetimeIndex):
        msg = "index_new should be a pandas.DatetimeIndex"
        raise TypeError(msg)

    series = series[series.index.notna() & series.notna()]
    dt = (series.index - series.index[0]) / pd.to_timedelta(1, unit="D")
    dt_interp = (index_new - series.index[0]) / pd.to_timedelta(1, unit="D")
    interp_obj = interpolate.interp1d(dt, series.values, bounds_error=False, **interp1d_kwargs)
    return pd.Series(interp_obj(dt_interp), index=index_new, name=series.name)
