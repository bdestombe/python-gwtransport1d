"""General utilities for the 1D groundwater transport model."""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import interpolate


def linear_interpolate(x_ref, y_ref, x_query, left=None, right=None):
    """
    Linear interpolation on monotonically increasing data.

    Parameters
    ----------
    x_ref : array-like
        Reference vector with sorted x-values.
    y_ref : array-like
        Reference vector with y-values.
    x_query : array-like
        Query x-values. Array may have any shape.
    left : float, optional
        Value to return for x_query < x_ref[0].
        - If `left` is set to None, x_query = x_ref[0].
        - If `left` is set to a float, such as np.nan, this value is returned.
    right : float, optional
        Value to return for x_query > x_ref[-1].
        - If `right` is set to None, x_query = x_ref[-1].
        - If `right` is set to a float, such as np.nan, this value is returned.

    Returns
    -------
    array
        Interpolated y-values.
    """
    x_ref = np.asarray(x_ref)
    y_ref = np.asarray(y_ref)
    x_query = np.asarray(x_query)

    # Find indices where x_query would be inserted in x_ref
    idx_no_edges = np.searchsorted(x_ref, x_query)

    idx = np.clip(idx_no_edges, 1, len(x_ref) - 1)

    # Calculate interpolation weights
    x0 = x_ref[idx - 1]
    x1 = x_ref[idx]
    y0 = y_ref[idx - 1]
    y1 = y_ref[idx]

    # Perform linear interpolation
    weights = (x_query - x0) / (x1 - x0)
    y_query = y0 + weights * (y1 - y0)

    # Handle edge cases
    if left is None:
        y_query = np.where(x_query < x_ref[0], y_ref[0], y_query)
    if right is None:
        y_query = np.where(x_query > x_ref[-1], y_ref[-1], y_query)
    if isinstance(left, float):
        y_query = np.where(x_query < x_ref[0], left, y_query)
    if isinstance(right, float):
        y_query = np.where(x_query > x_ref[-1], right, y_query)

    return y_query


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
    series = series[series.index.notna() & series.notna()]
    dt = (series.index - series.index[0]) / pd.to_timedelta(1, unit="D")
    dt_interp = (index_new - series.index[0]) / pd.to_timedelta(1, unit="D")
    interp_obj = interpolate.interp1d(dt, series.values, bounds_error=False, **interp1d_kwargs)
    return interp_obj(dt_interp)


def diff(a, alignment="centered"):
    """Compute the cell widths for a given array of cell coordinates.

    If alignment is "centered", the coordinates are assumed to be centered in the cells.
    If alignment is "left", the coordinates are assumed to be at the left edge of the cells.
    If alignment is "right", the coordinates are assumed to be at the right edge of the cells.

    Parameters
    ----------
    a : array-like
        Input array.

    Returns
    -------
    array
        Array with differences between elements.
    """
    if alignment == "centered":
        mid = a[:-1] + (a[1:] - a[:-1]) / 2
        return np.concatenate((a[[1]] - a[[0]], mid[1:] - mid[:-1], a[[-1]] - a[[-2]]))
    if alignment == "left":
        return np.concatenate((a[1:] - a[:-1], a[[-1]] - a[[-2]]))
    if alignment == "right":
        return np.concatenate((a[[1]] - a[[0]], a[1:] - a[:-1]))

    msg = f"Invalid alignment: {alignment}"
    raise ValueError(msg)


def linear_average(  # noqa: C901
    x_data: Sequence[float] | npt.NDArray[np.float64],
    y_data: Sequence[float] | npt.NDArray[np.float64],
    x_edges: Sequence[float] | npt.NDArray[np.float64],
    extrapolate_method: str = "nan",
) -> npt.NDArray[np.float64]:
    """
    Compute the average value of a piecewise linear time series between specified x-edges.

    Parameters
    ----------
    x_data : array-like
        x-coordinates of the time series data points, must be in ascending order
    y_data : array-like
        y-coordinates of the time series data points
    x_edges : array-like
        x-coordinates of the integration edges, must be in ascending order
    extrapolate_method : str, optional
        Method for handling extrapolation. Default is 'nan'.
        - 'outer': Extrapolate using the outermost data points.
        - 'nan': Extrapolate using np.nan.
        - 'raise': Raise an error for out-of-bounds values.

    Returns
    -------
    numpy.ndarray
        Array of average values between consecutive pairs of x_edges

    Examples
    --------
    >>> x_data = [0, 1, 2, 3]
    >>> y_data = [0, 1, 1, 0]
    >>> x_edges = [0, 1.5, 3]
    >>> linear_average(x_data, y_data, x_edges)
    array([0.667, 0.667])
    """
    show = ~np.isnan(x_data) & ~np.isnan(y_data)

    if show.sum() < 2:  # noqa: PLR2004
        return np.full(shape=len(x_edges) - 1, fill_value=np.nan)

    x_data = np.asarray(x_data, dtype=float)[show]
    y_data = np.asarray(y_data, dtype=float)[show]
    x_edges = np.asarray(x_edges, dtype=float)

    # Input validation
    if len(x_data) != len(y_data) and len(x_data) > 0:
        msg = "x_data and y_data must have the same length and be non-empty"
        raise ValueError(msg)
    if len(x_edges) < 2:  # noqa: PLR2004
        msg = "x_edges_in_range must contain at least 2 values"
        raise ValueError(msg)
    if not np.all(np.diff(x_data) >= 0):
        msg = "x_data must be in ascending order"
        raise ValueError(msg)
    if not np.all(np.diff(x_edges) >= 0):
        msg = "x_edges must be in ascending order"
        raise ValueError(msg)

    # Extrapolate
    if extrapolate_method == "outer":
        # bins with x_edges ouside the range of x_data should be nan
        # Zero-widths are handles at the end of this function
        x_edges_in_range = np.clip(x_edges, x_data.min(), x_data.max())
    elif extrapolate_method == "nan":
        # bins with x_edges ouside the range of x_data should be nan
        is_within_range = (x_edges >= x_data.min()) & (x_edges <= x_data.max())
        x_edges_in_range = x_edges[is_within_range]
    elif extrapolate_method == "raise":
        if np.any(x_edges < x_data.min()) or np.any(x_edges > x_data.max()):
            msg = "x_edges must be within the range of x_data"
            raise ValueError(msg)
    else:
        msg = "extrapolate_method must be 'outer', 'nan', or 'raise'"
        raise ValueError(msg)

    # Create a combined array of all x points
    all_x = np.concatenate([x_data, x_edges_in_range])

    # Get unique values and inverse indices
    unique_x, inverse_indices = np.unique(all_x, return_inverse=True)

    # Get indices of where the edges are in the unique array
    edge_indices = inverse_indices[len(x_data) : len(all_x)]

    # Interpolate y values at all unique x points
    unique_y = np.interp(unique_x, x_data, y_data, left=np.nan, right=np.nan)

    # Compute segment-wise integrals using the trapezoidal rule
    dx = np.diff(unique_x)
    y_avg = (unique_y[:-1] + unique_y[1:]) / 2
    segment_integrals = dx * y_avg

    # Compute cumulative integral
    cumulative_integral = np.concatenate([[0], np.cumsum(segment_integrals)])

    # Compute integral between consecutive edges
    integral_values = np.diff(cumulative_integral[edge_indices])

    # Compute widths between consecutive edges
    edge_widths = np.diff(x_edges_in_range)

    # Handle zero-width intervals and non-zero width intervals in a vectorized way
    zero_width_mask = edge_widths == 0

    # For non-zero width intervals, compute average = integral / width
    average_values_in_range = np.zeros_like(edge_widths)
    non_zero_mask = ~zero_width_mask
    if np.any(non_zero_mask):
        average_values_in_range[non_zero_mask] = integral_values[non_zero_mask] / edge_widths[non_zero_mask]

    # For zero-width intervals, get the y-value directly from unique_y using edge_indices
    if np.any(zero_width_mask):
        # The indices in unique_x for zero-width edge positions
        zero_width_indices = edge_indices[np.where(zero_width_mask)[0]]

        # Get all the y-values at once and assign them
        average_values_in_range[zero_width_mask] = unique_y[zero_width_indices]

    # Handle extrapolation when 'nan' method is used and some edges are outside data range
    if extrapolate_method == "nan" and ~np.all(is_within_range):
        # Identify which bins are completely within the data range
        bins_within_range = (x_edges[:-1] >= x_data.min()) & (x_edges[1:] <= x_data.max())
        # Create array of NaNs with same size as the number of bins
        average_values = np.full(shape=bins_within_range.size, fill_value=np.nan)
        # Copy calculated averages only to bins that are within data range
        average_values[bins_within_range] = average_values_in_range
        return average_values

    return average_values_in_range
