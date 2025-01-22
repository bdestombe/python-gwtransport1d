"""Module that implements diffusion."""

import numpy as np
from scipy import ndimage, sparse


def gaussian_filter_variable_sigma(input_signal, sigma_array, mode="reflect", truncate=4.0):
    """Apply Gaussian filter with position-dependent sigma values.

    This function extends scipy.ndimage.gaussian_filter1d by allowing the standard
    deviation (sigma) of the Gaussian kernel to vary at each point in the signal.
    It implements the filter using a sparse convolution matrix where each row
    represents a Gaussian kernel with a locally-appropriate standard deviation.

    Parameters
    ----------
    input_signal : ndarray
        One-dimensional input array to be filtered.
    sigma_array : ndarray
        One-dimensional array of standard deviation values, must have same length
        as input_signal. Each value specifies the Gaussian kernel width at the
        corresponding position.
    mode : {'reflect', 'constant', 'nearest', 'mirror', 'wrap'}, optional
        The mode parameter determines how the input array is extended when
        the filter overlaps a border. Default is 'reflect'.
    truncate : float, optional
        Truncate the filter at this many standard deviations.
        Default is 4.0.

    Returns
    -------
    ndarray
        The filtered input signal. Has the same shape as input_signal.

    Notes
    -----
    The function constructs a sparse convolution matrix where each row represents
    a position-specific Gaussian kernel. The kernel width adapts to local sigma
    values, making it suitable for problems with varying diffusion coefficients
    or time steps.

    For diffusion problems, the local sigma values can be calculated as:
    sigma = sqrt(2 * diffusion_coefficient * dt) / dx
    where diffusion_coefficient is the diffusion coefficient, dt is the time step, and dx is the
    spatial step size.

    The implementation uses sparse matrices for memory efficiency when dealing
    with large signals or when sigma values vary significantly.

    See Also
    --------
    scipy.ndimage.gaussian_filter1d : Fixed-sigma Gaussian filtering
    scipy.sparse : Sparse matrix implementations

    Examples
    --------
    >>> # Create a sample signal
    >>> x = np.linspace(0, 10, 1000)
    >>> signal = np.exp(-((x - 3) ** 2)) + 0.5 * np.exp(-((x - 7) ** 2) / 0.5)

    >>> # Create position-dependent sigma values
    >>> diffusion_coefficient = 0.1  # Diffusion coefficient
    >>> dt = 0.001 * (1 + np.sin(2 * np.pi * x / 10))  # Varying time steps
    >>> dx = x[1] - x[0]
    >>> sigma_array = np.sqrt(2 * diffusion_coefficient * dt) / dx

    >>> # Apply the filter
    >>> filtered = gaussian_filter_variable_sigma(signal, sigma_array)
    """
    if len(input_signal) != len(sigma_array):
        msg = "Input signal and sigma array must have the same length"
        raise ValueError(msg)

    if mode not in {"reflect", "constant", "nearest", "mirror", "wrap"}:
        msg = f"Invalid mode: {mode}"
        raise ValueError(msg)

    n = len(input_signal)

    # Handle zero sigma values
    zero_mask = sigma_array == 0
    if np.all(zero_mask):
        return input_signal.copy()

    # Get maximum kernel size and create position arrays
    max_sigma = np.max(sigma_array)
    max_radius = int(truncate * max_sigma + 0.5)

    # Create arrays for all possible kernel positions
    positions = np.arange(-max_radius, max_radius + 1)

    # Create a mask for valid sigma values
    valid_sigma = ~zero_mask
    valid_indices = np.where(valid_sigma)[0]

    # Create position matrices for broadcasting
    # Shape: (n_valid_points, 1)
    center_positions = valid_indices[:, np.newaxis]
    # Shape: (1, max_kernel_size)
    kernel_positions = positions[np.newaxis, :]

    # Calculate the relative positions for each point
    # This creates a matrix of shape (n_valid_points, max_kernel_size)
    relative_positions = kernel_positions

    # Calculate Gaussian weights for all positions at once
    # Using broadcasting to create a matrix of shape (n_valid_points, max_kernel_size)
    sigmas = sigma_array[valid_sigma][:, np.newaxis]
    weights = np.exp(-0.5 * (relative_positions / sigmas) ** 2)

    # Normalize each kernel
    weights /= np.sum(weights, axis=1)[:, np.newaxis]

    # Calculate absolute positions in the signal
    absolute_positions = center_positions + relative_positions

    # Handle boundary conditions
    if mode == "wrap":
        absolute_positions %= n
    elif mode == "reflect":
        absolute_positions = np.clip(absolute_positions, 0, n - 1)
        reflect_mask = absolute_positions >= n
        absolute_positions[reflect_mask] = 2 * (n - 1) - absolute_positions[reflect_mask]
        reflect_mask = absolute_positions < 0
        absolute_positions[reflect_mask] = -absolute_positions[reflect_mask]
    elif mode == "constant":
        valid_mask = (absolute_positions >= 0) & (absolute_positions < n)
        weights[~valid_mask] = 0
    elif mode == "mirror":
        absolute_positions = np.clip(absolute_positions, 0, n - 1)
    # 'nearest' is handled by clipping
    absolute_positions = np.clip(absolute_positions, 0, n - 1)

    # Create coordinate arrays for sparse matrix
    rows = np.repeat(center_positions, weights.shape[1])
    cols = absolute_positions.ravel()
    data = weights.ravel()

    # Remove zero weights to save memory
    nonzero_mask = data != 0
    rows = rows[nonzero_mask]
    cols = cols[nonzero_mask]
    data = data[nonzero_mask]

    # Add identity matrix elements for zero-sigma positions
    if np.any(zero_mask):
        zero_indices = np.where(zero_mask)[0]
        rows = np.concatenate([rows, zero_indices])
        cols = np.concatenate([cols, zero_indices])
        data = np.concatenate([data, np.ones(len(zero_indices))])

    # Create the sparse matrix
    conv_matrix = sparse.csr_matrix((data, (rows, cols)), shape=(n, n))

    # Apply the filter
    return conv_matrix.dot(input_signal)


def create_example_diffusion_data(nx=1000, domain_length=10.0, diffusion_coefficient=0.1):
    """Create example data for demonstrating variable-sigma diffusion.

    Parameters
    ----------
    nx : int, optional
        Number of spatial points. Default is 1000.
    domain_length : float, optional
        Domain length. Default is 10.0.
    diffusion_coefficient : float, optional
        Diffusion coefficient. Default is 0.1.

    Returns
    -------
    x : ndarray
        Spatial coordinates.
    signal : ndarray
        Initial signal (sum of two Gaussians).
    sigma_array : ndarray
        Array of sigma values varying in space.
    dt : ndarray
        Array of time steps varying in space.

    Notes
    -----
    This function creates a test case with:
    - A signal composed of two Gaussian peaks
    - Sinusoidally varying time steps
    - Corresponding sigma values for diffusion
    """
    # Create spatial grid
    x = np.linspace(0, domain_length, nx)
    dx = x[1] - x[0]

    # Create initial signal (two Gaussians)
    signal = np.exp(-((x - 3) ** 2)) + 0.5 * np.exp(-((x - 7) ** 2) / 0.5) + 0.1 * np.random.randn(nx)

    # Create varying time steps
    dt = 0.001 * (1 + np.sin(2 * np.pi * x / domain_length))

    # Calculate corresponding sigma values
    sigma_array = np.sqrt(2 * diffusion_coefficient * dt) / dx

    return x, signal, sigma_array, dt


if __name__ == "__main__":
    from matplotlib import pyplot as plt

    # Generate example data
    x, signal, sigma_array, dt = create_example_diffusion_data()

    # Apply variable-sigma filtering
    filtered = gaussian_filter_variable_sigma(signal, sigma_array * 5)

    # Compare with regular Gaussian filter
    avg_sigma = np.mean(sigma_array)
    regular_filtered = ndimage.gaussian_filter1d(signal, avg_sigma)
    plt.figure(figsize=(10, 6))
    plt.plot(x, signal, label="Original signal", lw=0.8)
    plt.plot(x, filtered, label="Variable-sigma filtered", lw=1.0)

    plt.plot(x, regular_filtered, label="Regular Gaussian filter", lw=0.8, ls="--")
