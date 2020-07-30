import numpy as np
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import scipy.linalg as scila
import time

from structured_dpp.factor_tree import *
from min_energy_path.gaussian_field import gaussian_field, gaussian_field_grad, plot_gaussian
from min_energy_path.guassian_params import medium3d
from min_energy_path.points_sphere import create_sphere_points, plot_scatter_with_minima


start_time = time.time()


# First set up some constants we're going to need
N_SPANNING_GAP = 7
N_VARIABLES = N_SPANNING_GAP + 1

TUNING_STRENGTH = 1.5
TUNING_STRENGTH_DIFF = 3
TUNING_GRAD = 0.5
TUNING_DIST = .25
LENGTH_CUTOFF = 4

# Constants relating to the gaussian field
MIX_MAG, MIX_SIG, MIX_CENTRE, MINIMA_COORDS, XBOUNDS, YBOUNDS, ZBOUNDS = medium3d()

POINTS_INFO = create_sphere_points(MINIMA_COORDS, N_SPANNING_GAP)
SPHERE_BEFORE = POINTS_INFO['sphere_before']
SPHERE = POINTS_INFO['sphere']
SPHERE_INDEX = np.arange(SPHERE.shape[1])
N_TOTAL = POINTS_INFO['n_total']
BASIS = POINTS_INFO['basis']
MINIMA_DISTANCE = POINTS_INFO['minima_distance']
POINT_DISTANCE = POINTS_INFO['point_distance']
N_OVERFLOW = POINTS_INFO['n_overflow']
DIR_COMPONENT = POINTS_INFO['dir_component']

# Plot the space we're exploring
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
plot_scatter_with_minima(SPHERE, MINIMA_COORDS, ax)

# Find the minima indices
ROOT_INDEX, TAIL_INDEX = None, None
for i, point in enumerate(SPHERE.T):
    if np.allclose(point, MINIMA_COORDS[:, 0]):
        ROOT_INDEX = i
    if np.allclose(point, MINIMA_COORDS[:, 1]):
        TAIL_INDEX = i
if None in [ROOT_INDEX, TAIL_INDEX]:
    raise ValueError("Couldn't find root or tail index.")
ROOT_DIR_INDEX = np.where(DIR_COMPONENT == SPHERE_BEFORE[0, ROOT_INDEX])[0][0]


@assignment_to_var_arguments
def intermediate_factor_quality_breakdown(idx1, idx2):
    if idx1 == idx2:
        return 0, 0, 0, 0
    pos = SPHERE[:, [idx1, idx2]]
    pos1, pos2 = pos.T
    midpoint = (pos1 + pos2) / 2
    pos = np.concatenate((pos, midpoint[:, np.newaxis]), axis=1)

    direction = pos2 - pos1
    length = scila.norm(direction)
    if length >= LENGTH_CUTOFF * POINT_DISTANCE:
        return 0, 0, 0, 0
    direction_normed = direction/length
    dist_quality = np.exp(-TUNING_DIST*length/(2*POINT_DISTANCE))

    strength = gaussian_field(pos, MIX_MAG, MIX_SIG, MIX_CENTRE)
    strength_diff = strength[0] - strength[1]  # Strength 1 is closer to the root, as it is the parent
    strength_diff_quality = np.exp(-TUNING_STRENGTH_DIFF*strength_diff) if strength_diff > 0 else 1
    strength_quality = np.exp(-TUNING_STRENGTH*np.sum(strength)/3)

    grad = gaussian_field_grad(midpoint[:, np.newaxis], MIX_MAG, MIX_SIG, MIX_CENTRE)[:, 0]
    grad_perp = grad - np.dot(grad, direction_normed) * direction_normed
    grad_quality = np.exp(-TUNING_GRAD*scila.norm(grad_perp))
    return strength_quality, strength_diff_quality, dist_quality, grad_quality


@assignment_to_var_arguments
def intermediate_factor_quality(idx1, idx2):  # idx2 closer to the root
    if idx1 == idx2:
        return 0
    pos = SPHERE[:, [idx1, idx2]]
    pos1, pos2 = pos.T
    midpoint = (pos1 + pos2) / 2
    pos = np.concatenate((pos, midpoint[:, np.newaxis]), axis=1)

    direction = pos2 - pos1
    length = scila.norm(direction)
    if length >= LENGTH_CUTOFF * POINT_DISTANCE:
        return 0
    direction_normed = direction/length
    dist_quality = np.exp(-TUNING_DIST*length/(2*POINT_DISTANCE))

    strength = gaussian_field(pos, MIX_MAG, MIX_SIG, MIX_CENTRE)
    strength_diff = strength[0] - strength[1]  # Strength 1 is closer to the root, as it is the parent
    strength_diff_quality = np.exp(-TUNING_STRENGTH_DIFF*strength_diff) if strength_diff > 0 else 1
    strength_quality = np.exp(-TUNING_STRENGTH*np.sum(strength)/3)

    grad = gaussian_field_grad(midpoint[:, np.newaxis], MIX_MAG, MIX_SIG, MIX_CENTRE)[:, 0]
    grad_perp = grad - np.dot(grad, direction_normed) * direction_normed
    grad_quality = np.exp(-TUNING_GRAD*scila.norm(grad_perp))
    return strength_quality*strength_diff_quality*dist_quality*grad_quality


def error_diversity(*args):
    raise Exception("This shouldn't run")


current_var = Variable((ROOT_INDEX,), name='RootVar0')
nodes_to_add = [current_var]
for i in range(1, N_VARIABLES):
    # Add transition factor
    transition_factor = SDPPFactor(intermediate_factor_quality,
                                   error_diversity,
                                   parent=current_var,
                                   name=f'Fac{i-1}-{i}')
    nodes_to_add.append(transition_factor)

    if i == N_VARIABLES - 1:
        current_var = Variable((TAIL_INDEX,),
                               parent=transition_factor,
                               name=f'TailVar{i}')
    else:
        # Sphere slice bounds
        slice_of_dir = DIR_COMPONENT[max(ROOT_DIR_INDEX+i-1, 0):ROOT_DIR_INDEX+i+2]
        in_slice = (np.min(slice_of_dir) <= SPHERE_BEFORE[0, :]) & (SPHERE_BEFORE[0, :] <= np.max(slice_of_dir))

        current_var = Variable(SPHERE_INDEX[in_slice].T,
                               parent=transition_factor,
                               name=f'Var{i}')
    nodes_to_add.append(current_var)

ftree = SDPPFactorTree.create_from_connected_nodes(nodes_to_add)

def get_good_max_samples(var: Variable, run, n_per_group=3):
    groups = {}
    for idx in var.allowed_values:
        group = tuple(SPHERE_BEFORE[1:, idx] / POINT_DISTANCE // n_per_group)
        value = var.outgoing_messages[run][None][idx]
        route_before = groups.get(group, None)
        if route_before is None or value > route_before[1]:
            groups[group] = (idx, value)
    return groups

index_of_middle = len(nodes_to_add) // 2
var5 = nodes_to_add[index_of_middle - (index_of_middle % 2) - 2]

traversal, run = ftree.run_max_quality_forward(var5)
good_max_samples = get_good_max_samples(var5, run, 4)
assignments = [ftree.get_max_from_start_assignment(var5, good_max_idx, traversal, run)
               for good_max_idx, good_max in good_max_samples.values()]

print(f'Running time {time.time() - start_time}')

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.set_xlabel('x')
ax.set_ylabel('y')
ax.set_zlabel('z')

ax.scatter(*MIX_CENTRE, c=MIX_MAG, s=40*MIX_SIG)

var5_max_beliefs: dict = var5.outgoing_messages[MaxProductRun()][None]

for assignment, (grp, (good_max_idx, good_max)) in zip(assignments, good_max_samples.items()):
    points = np.array([
        SPHERE[:, assignment[var]] for var in ftree.get_variables()
    ]).T
    ax.plot(*points, label=f'{grp}')
    print(grp, good_max)


plt.legend()
plt.show()

# Examining group (0, 0)
good_maxs = list(zip(assignments, good_max_samples.items()))
assignment = good_maxs[4][0]
quality_breakdown = [1, 1, 1, 1]
for node in ftree.get_nodes():
     if isinstance(node, SDPPFactor):
         fac_qual_breakdown = intermediate_factor_quality_breakdown(node, assignment)
         print(node, fac_qual_breakdown)
         quality_breakdown = [q1 * q2 for q1, q2 in zip(quality_breakdown, fac_qual_breakdown)]
     else:
         print(node, SPHERE[:, assignment[node]])
print('Overall', quality_breakdown)
