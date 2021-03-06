"""
A file to implement NEB.

Credit to https://github.com/adamfrees/NudgedElasticBand
I copied his algorithm
"""
import numpy as np
import scipy.linalg as scila
import logging

import min_energy_path.gaussian_field as gf


logger = logging.getLogger(__name__)


def plot_paths_and_tangents(path, tangent, scale=5, width=0.025):
    plt.plot(*old_path)
    plt.plot(*path)
    for (x, y), (dx, dy) in zip(path[:, 1:-1].T, tangent.T):
        plt.arrow(x, y, dx/scale, dy/scale, width=width)
    plt.gca().axis('equal')
    plt.show()


def neb(path_guess, mix_params, force_cutoff=10**-5, n_max_iterations=8000, k=1., time_step=1.e-2, return_force_history=False):
    """
    Performs the NEB algorithm
    :param np.ndarray path_guess:
        Matrix (d dimensions, n points) of the points on the initial path guess
    :param mix_params:
        The generated dictionary of gaussian mix params
    :param force_cutoff:
        If the force's L2 norm is below this cutoff then the path quits
    :param n_max_iterations:
        Number of iterations to perform on the path
    :param k:
        The spring force component
    :param time_step:
        The size of the step to take during an interation
    :param return_force_history:
        If True returns the force L2 norm for each iteration
    :return:
    """
    logger.info('Starting neb run')

    path = path_guess.copy()

    velocity = np.zeros((path.shape[0], path.shape[1]-2))
    old_force = np.zeros_like(velocity)

    force_history = []

    tangents = np.zeros((path.shape[0], path.shape[1]-2))

    for i in range(n_max_iterations):
        # Calculate the energy at each point
        coords_transformed = gf.transform_coords(path, mix_params)
        field_strength = gf._field_strength(coords_transformed, mix_params)
        path_energies = np.sum(field_strength, axis=1)

        # Calculate the tangents
        tip = path[:, 2:] - path[:, 1:-1]  # Tangent by difference to element in front
        tim = path[:, 1:-1] - path[:, :-2]  # Tangent by difference to element behind
        # From element 0 to n-1 is the next element bigger
        # Also from element 1 to n is the previous element smaller
        next_bigger = path_energies[:-1] < path_energies[1:]

        energy_increasing = next_bigger[1:] & next_bigger[:-1]  # From element 1 to n-1 is E{i-1} < E{i} < E{i+1}
        tangents[:, energy_increasing] = tip[:, energy_increasing]

        energy_decreasing = (~next_bigger[1:]) & (~next_bigger[:-1])  # From element 1 to n-1 is E{i-1} > E{i} > E{i+1}
        tangents[:, energy_decreasing] = tim[:, energy_decreasing]

        # Critical points have a slightly different formula
        # From element 1 to n-1 is it a max or min to its neighbors
        at_critical = (~energy_increasing) & (~energy_decreasing)
        # From element 1 to n-1 that are critical points the abs difference to the next element
        next_next_bigger = path_energies[:-2] < path_energies[2:]  # From element 1 to n-1 is E{i-1} < E{i+1}
        # Difference of critical points to point after
        delta_e_forward = np.abs(path_energies[1:-1][at_critical] - path_energies[2:][at_critical])
        delta_e_back = np.abs(path_energies[1:-1][at_critical] - path_energies[:-2][at_critical])
        delta_e_table = np.array([delta_e_forward,
                                  delta_e_back])
        delta_e_max = np.max(delta_e_table, axis=0)
        delta_e_min = np.min(delta_e_table, axis=0)
        tangents[:, at_critical & next_next_bigger] = (
                tip[:, at_critical & next_next_bigger]*delta_e_max[np.newaxis, next_next_bigger[at_critical]] +
                tim[:, at_critical & next_next_bigger]*delta_e_min[np.newaxis, next_next_bigger[at_critical]]
        )
        tangents[:, at_critical & (~next_next_bigger)] = (
                tip[:, at_critical & (~next_next_bigger)]*delta_e_min[np.newaxis, ~next_next_bigger[at_critical]] +
                tim[:, at_critical & (~next_next_bigger)]*delta_e_max[np.newaxis, ~next_next_bigger[at_critical]]
        )
        tang_norm = scila.norm(tangents, axis=0, keepdims=True)
        if np.any(tang_norm < 1e-20):
            logger.error(f"Tangent norm less than 1e-20 returning early after {i+1} iterations")
            if return_force_history:
                return path, force_history
            return path
        tangents /= scila.norm(tangents, axis=0, keepdims=True)  # TODO: What if two points land on each other?

        # Calculate the distance between the points
        transitions = path[:, 1:] - path[:, :-1]
        point_distances = scila.norm(transitions, axis=0, keepdims=True)

        # Spring force component!
        spring_component = k*(point_distances[:, 1:] - point_distances[:, :-1])*tangents

        # Tangential gradient component
        gradients = gf._gaussian_grad(coords_transformed[:, 1:-1, :], field_strength[1:-1, :], mix_params)
        orth_grad_component = gradients - np.sum(gradients * tangents, axis=0, keepdims=True)*tangents

        # Apply forces using gradient
        force = spring_component - orth_grad_component
        force_l2 = scila.norm(force)
        force_history.append(force_l2)
        if force_l2 < force_cutoff:
            logger.info(f'Finished NEB from force cutoff after {i+1} iterations')
            if return_force_history:
                return path, force_history
            return path

        force_velocity = velocity * force
        if np.sum(force_velocity) > 0:
            velocity = force_velocity * force / scila.norm(force)**2
            velocity += (old_force+force) / 2.
        else:
            velocity = (old_force + force) / 2.

        path[:, 1:-1] += velocity * time_step

        old_force = force

    logger.info(f'Finished NEB from max_iterations after {n_max_iterations} iterations with force {force_l2}')

    if return_force_history:
        return path, force_history
    return path


def neb_mep(mepath_info, points_info, mix_params, n_spanning_point_gap=3, force_cutoff=1e-6, n_max_iterations=3000, k=1., time_step=1.e-2):
    """
    Performs the NEB algorithm on the MEP generated path
    :param mepath_info:
        The generated path_info dictionary
    :param points_info:
        The generated point_info dictionary
    :param n_spanning_point_gap:
        The number of NEB points to span the MEP point gap
    :param mix_params:
        The generated dictionary of gaussian mix params
    :param force_cutoff:
        If the force's L2 norm is below this cutoff then the path quits
    :param n_max_iterations:
        Number of iterations to perform on the path
    :param k:
        The spring force component
    :param time_step:
        The size of the step to take during an interation
    :return:
    """
    # First check if the path ever crosses the same point twice
    # If it does, delete it!
    new_path_points = []
    i = 0
    path_indexes = mepath_info['path_indexes']
    while i < len(path_indexes):
        new_path_points.append(i)
        # Check no next point goes through the same point
        for j in range(i+1, len(path_indexes)):
            if path_indexes[i] == path_indexes[j]:
                i = j  # Set i to j, skipping points in between
        if i == len(path_indexes) - 2:
            i += 1
            continue
        if i == len(path_indexes) - 1:
            break
        # Check the next point doesn't go through the same point in the opposite direction
        next_dir = mepath_info['path'][:, i+1] - mepath_info['path'][:, i]
        next_dir /= scila.norm(next_dir)
        next_next_dir = mepath_info['path'][:, i+2] - mepath_info['path'][:, i+1]
        next_next_dir /= scila.norm(next_next_dir)
        if np.allclose(next_dir, next_next_dir) or np.allclose(next_dir, -next_next_dir):
            i += 2
        else:
            i += 1

    new_mep_path = mepath_info['path'][:, new_path_points]

    neb_start_path = []
    for i in range(new_mep_path.shape[1]-1):
        p0 = new_mep_path[:, i]
        p1 = new_mep_path[:, i+1]
        dist = scila.norm(p1 - p0) / points_info['point_distance']
        n_points = int(np.floor((dist * n_spanning_point_gap) + 1e-4))
        points = np.linspace(p0, p1, n_points, endpoint=False, axis=-1)
        points += ((p1-p0)/(2*n_points))[:, np.newaxis]  # Shift the points so that they are equidistant from both end points
        neb_start_path.append(points)

    neb_start_path = np.concatenate(neb_start_path, axis=1)

    return neb(neb_start_path, mix_params, force_cutoff, n_max_iterations, k, time_step)


if __name__ == '__main__':
    from min_energy_path import gaussian_params
    from min_energy_path.gaussian_field import plot_gaussian
    import matplotlib.pyplot as plt

    logging.basicConfig(level=logging.INFO)

    _mix_params = gaussian_params.starter()
    old_path = np.linspace(_mix_params['minima_coords'][:, 0], _mix_params['minima_coords'][:, 1], 15, axis=-1)
    new_path, force_history = neb(old_path, _mix_params, n_max_iterations=10**5, return_force_history=True)

    plot_gaussian(_mix_params)
    plt.plot(*old_path, 'bo-')
    plt.plot(*new_path, 'ro-')
    plt.show()

    fig, ax = plt.subplots()
    ax.semilogy(force_history)
    ax.set_xlabel('Iterations')
    ax.set_ylabel('Frob norm of force')
    ax.set_title('NEB change of force over iterations')
    fig.show()
