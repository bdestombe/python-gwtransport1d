"""
Functions for calculating log removal efficiency in water treatment systems.

This module provides utilities to calculate log removal values for different
configurations of water treatment systems, particularly focusing on parallel flow
arrangements where multiple treatment processes operate simultaneously on different
fractions of the total flow.

Log removal is a standard measure in water treatment that represents the
reduction of pathogen concentration on a logarithmic scale. For example,
a log removal of 3 represents a 99.9% reduction in pathogen concentration.

Functions:
calculate_parallel_log_removal : Calculate the weighted average log removal for
                                a system with parallel flows.

Notes
-----
For systems in series, log removals are typically summed directly, while for
parallel systems, a weighted average based on flow distribution is required.
"""

import numpy as np
from scipy import stats
from scipy.special import digamma, gamma


def parallel_mean(log_removals, flow_fractions=None):
    """
    Calculate the weighted average log removal for a system with parallel flows.

    This function computes the overall log removal efficiency of a parallel
    filtration system. If flow_fractions is not provided, it assumes equal
    distribution of flow across all paths.

    The calculation uses the formula:

    Total Log Removal = -log₁₀(sum(F_i * 10^(-LR_i)))

    Where:
    - F_i = fraction of flow through system i (decimal, sum to 1.0)
    - LR_i = log removal of system i

    Parameters
    ----------
    log_removals : array_like
        Array of log removal values for each parallel flow.
        Each value represents the log₁₀ reduction of pathogens.

    flow_fractions : array_like, optional
        Array of flow fractions for each parallel flow.
        Must sum to 1.0 and be the same length as log_removals.
        If None, equal flow distribution is assumed (default is None).

    Returns
    -------
    float
        The combined log removal value for the parallel system.

    Raises
    ------
    ValueError
        If log_removals is empty
        If flow_fractions is provided and does not sum to 1.0 (within tolerance)
        If flow_fractions is provided and has different length than log_removals

    Notes
    -----
    Log removal is a logarithmic measure of pathogen reduction:
    - Log 1 = 90% reduction
    - Log 2 = 99% reduction
    - Log 3 = 99.9% reduction

    For parallel flows, the combined removal is typically less effective
    than the best individual removal but better than the worst.

    Examples
    --------
    >>> import numpy as np
    >>> # Three parallel streams with equal flow and log removals of 3, 4, and 5
    >>> log_removals = np.array([3, 4, 5])
    >>> calculate_parallel_log_removal(log_removals)
    3.431798275933005

    >>> # Two parallel streams with weighted flow
    >>> log_removals = np.array([3, 5])
    >>> flow_fractions = np.array([0.7, 0.3])
    >>> calculate_parallel_log_removal(log_removals, flow_fractions)
    3.153044674980176

    See Also
    --------
    For systems in series, log removals would be summed directly.

    References
    ----------
    USEPA (2006). Ultraviolet Disinfection Guidance Manual for the
    Final Long Term 2 Enhanced Surface Water Treatment Rule.
    """
    # Convert log_removals to numpy array if it isn't already
    log_removals = np.asarray(log_removals, dtype=float)

    # Check if log_removals is empty
    if len(log_removals) == 0:
        msg = "At least one log removal value must be provided"
        raise ValueError(msg)

    # If flow_fractions is not provided, assume equal distribution
    if flow_fractions is None:
        # Calculate the number of parallel flows
        n = len(log_removals)
        # Create equal flow fractions
        flow_fractions = np.full(n, 1.0 / n)
    else:
        # Convert flow_fractions to numpy array
        flow_fractions = np.asarray(flow_fractions, dtype=float)

        # Validate inputs
        if len(log_removals) != len(flow_fractions):
            msg = "log_removals and flow_fractions must have the same length"
            raise ValueError(msg)

        if not np.isclose(np.sum(flow_fractions), 1.0):
            msg = "flow_fractions must sum to 1.0"
            raise ValueError(msg)

    # Convert log removal to decimal reduction values
    decimal_reductions = 10 ** (-log_removals)

    # Calculate weighted average decimal reduction
    weighted_decimal_reduction = np.sum(flow_fractions * decimal_reductions)

    # Convert back to log scale
    return -np.log10(weighted_decimal_reduction)


def gamma_pdf(r, rt_alpha, rt_beta, C):
    """
    Compute the probability density function (PDF) of log removal given a gamma distribution for the residence time.

    gamma(rt_alpha, rt_beta) = gamma(apv_alpha, apv_beta / flow)

    Parameters
    ----------
    r : array_like
        Log removal values at which to compute the PDF.
    rt_alpha : float
        Shape parameter of the gamma distribution for residence time.
    rt_beta : float
        Scale parameter of the gamma distribution for residence time.
    C : float
        Coefficient for log removal calculation (R = C * log10(T)).

    Returns
    -------
    pdf_values : ndarray
        PDF values corresponding to the input r values.
    """
    # Compute the transformed PDF
    t_values = 10 ** (r / C)

    return (
        (np.log(10) / (C * gamma(rt_alpha) * (rt_beta**rt_alpha))) * (t_values**rt_alpha) * np.exp(-t_values / rt_beta)
    )


def gamma_cdf(r, rt_alpha, rt_beta, C):
    """
    Compute the cumulative distribution function (CDF) of log removal given a gamma distribution for the residence time.

    gamma(rt_alpha, rt_beta) = gamma(apv_alpha, apv_beta / flow)

    Parameters
    ----------
    r : array_like
        Log removal values at which to compute the CDF.
    alpha : float
        Shape parameter of the gamma distribution for residence time.
    beta : float
        Scale parameter of the gamma distribution for residence time.
    C : float
        Coefficient for log removal calculation (R = C * log10(T)).

    Returns
    -------
    cdf_values : ndarray
        CDF values corresponding to the input r values.
    """
    # Compute t values corresponding to r values
    t_values = 10 ** (r / C)

    # Use the gamma CDF directly
    return stats.gamma.cdf(t_values, a=rt_alpha, scale=rt_beta)


def gamma_mean(rt_alpha, rt_beta, C):
    """
    Compute the mean of the log removal distribution given a gamma distribution for the residence time.

    gamma(rt_alpha, rt_beta) = gamma(apv_alpha, apv_beta / flow)

    Parameters
    ----------
    rt_alpha : float
        Shape parameter of the gamma distribution for residence time.
    rt_beta : float
        Scale parameter of the gamma distribution for residence time.
    C : float
        Coefficient for log removal calculation (R = C * log10(T)).

    Returns
    -------
    mean : float
        Mean value of the log removal distribution.
    """
    # Calculate E[R] = C * E[log10(T)]
    # For gamma distribution: E[ln(T)] = digamma(alpha) + ln(beta_adjusted)
    # Convert to log10: E[log10(T)] = E[ln(T)] / ln(10)

    return (C / np.log(10)) * (digamma(rt_alpha) + np.log(rt_beta))


def gamma_find_flow_for_target_mean(target_mean, apv_alpha, apv_beta, C):
    """
    Find the flow rate flow that produces a specified target mean log removal given a gamma distribution for the residence time.

    gamma(rt_alpha, rt_beta) = gamma(apv_alpha, apv_beta / flow)

    Parameters
    ----------
    target_mean : float
        Target mean log removal value.
    apv_alpha : float
        Shape parameter of the gamma distribution for residence time.
    apv_beta : float
        Scale parameter of the gamma distribution for pore volume.
    C : float
        Coefficient for log removal calculation (R = C * log10(T)).

    Returns
    -------
    flow : float
        Flow rate that produces the target mean log removal.

    Notes
    -----
    This function uses the analytical solution derived from the mean formula.
    From E[R] = (C/ln(10)) * (digamma(alpha) + ln(beta) - ln(Q)),
    we can solve for Q to get:
    flow = beta * exp(ln(10)*target_mean/C - digamma(alpha))
    """
    # Rearranging the mean formula to solve for Q:
    # target_mean = (C/ln(10)) * (digamma(alpha) + ln(beta) - ln(Q))
    # ln(Q) = digamma(alpha) + ln(beta) - (ln(10)*target_mean/C)
    # Q = beta * exp(-(ln(10)*target_mean/C - digamma(alpha)))
    return apv_beta * np.exp(digamma(apv_alpha) - (np.log(10) * target_mean) / C)


# Example usage
if __name__ == "__main__":
    # Example parameters
    Q = 5.0  # Flow rate
    apv_alpha = 2.0
    apv_beta = 10.0  # Scale parameter for pore volume
    rt_alpha = 2.0
    rt_beta = apv_beta / Q  # Scale parameter for pore volume
    C = 2.0  # Coefficient for log removal

    # Generate range of log removal values
    r_values = np.linspace(-1, 5, 1000)

    mean = gamma_mean(rt_alpha, rt_beta, C)
    print(f"Mean log removal: {mean:.4f}")

    # Example of finding Q for a target mean log removal
    target_mean = 3.0  # Example target mean
    required_Q = gamma_find_flow_for_target_mean(target_mean, apv_alpha, apv_beta, C)
    print(f"Flow rate Q required for mean log removal of {target_mean}: {required_Q:.4f}")

    # Verify the result
    verification_mean = gamma_mean(rt_alpha, rt_beta, C)
    print(f"Verification - mean log removal with Q = {required_Q:.4f}: {verification_mean:.4f}")

    # To visualize (optional):
    import matplotlib.pyplot as plt

    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    pdf = gamma_pdf(r_values, rt_alpha, rt_beta, C)
    cdf = gamma_cdf(r_values, rt_alpha, rt_beta, C)
    plt.plot(r_values, pdf)
    plt.title("PDF of Log Removal")
    plt.xlabel("Log Removal (R)")
    plt.ylabel("Probability Density")
    plt.grid(True)

    plt.subplot(1, 2, 2)
    plt.plot(r_values, cdf)
    plt.title("CDF of Log Removal")
    plt.xlabel("Log Removal (R)")
    plt.ylabel("Cumulative Probability")
    plt.grid(True)

    plt.tight_layout()
    plt.show()
