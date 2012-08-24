import numpy
from tigger.cluda.helpers import *

TEMPLATE = template_for(__file__)


class VirtualSizes:

    def __init__(self, device_params, global_size, local_size):
        self.params = device_params

        if isinstance(global_size, int):
            global_size = (global_size,)

        if isinstance(local_size, int):
            local_size = (local_size,)

        self.global_size = global_size
        self.local_size = local_size

        if len(self.global_size) != len(self.local_size):
            raise ValueError("Global/local work sizes have differing dimensions")
        if len(self.global_size) > 3:
            raise ValueError("Virtual sizes are supported for 1D to 3D grids only")

        self.naive_bounding_grid = [min_blocks(gs, ls)
            for gs, ls in zip(self.global_size, self.local_size)]

        if product(self.local_size) > self.params.max_work_group_size:
            raise ValueError("Number of work items is too high")
        if product(self.naive_bounding_grid) > product(self.params.max_grid_sizes):
            raise ValueError("Number of work groups is too high")

        self.grid_parts = self.get_rearranged_grid(self.naive_bounding_grid)
        gdims = len(self.params.max_grid_sizes)
        self.grid = [product([row[i] for row in self.grid_parts])
            for i in xrange(gdims)]
        self.k_local_size = list(self.local_size) + [1] * (gdims - len(self.local_size))
        self.k_global_size = [l * g for l, g in zip(self.k_local_size, self.grid)]

    def get_rearranged_grid(self, grid):
        # This algorithm can be made much better, but at the moment we have a simple implementation
        # The guidelines are:
        # 1) the order of array elements should be preserved (so it is like a reshape() operation)
        # 2) the overhead of empty threads is considered negligible
        #    (usually it will be true because it will be hidden by global memory latency)
        # 3) assuming len(grid) <= 3
        max_grid = self.params.max_grid_sizes
        if len(grid) == 1:
            return self.get_rearranged_grid_1d(grid, max_grid)
        elif len(grid) == 2:
            return self.get_rearranged_grid_2d(grid, max_grid)
        elif len(grid) == 3:
            return self.get_rearranged_grid_3d(grid, max_grid)
        else:
            raise NotImplementedError()

    def get_rearranged_grid_2d(self, grid, max_grid):
        # A dumb algorithm which relies on 1d version
        grid1 = self.get_rearranged_grid_1d([grid[0]], max_grid)

        # trying to fit in remaining dimensions, to decrease the number of operations
        # in get_group_id()
        new_max_grid = [mg / g1d for mg, g1d in zip(max_grid, grid1[0])]
        if product(new_max_grid[1:]) >= grid[1]:
            grid2 = self.get_rearranged_grid_1d([grid[1]], new_max_grid[1:])
            grid2 = [[1] + grid2[0]]
        else:
            grid2 = self.get_rearranged_grid_1d([grid[1]], new_max_grid)

        return grid1 + grid2

    def get_rearranged_grid_3d(self, grid, max_grid):
        # same dumb algorithm, but relying on 2d version
        grid1 = self.get_rearranged_grid_2d(grid[:2], max_grid)

        # trying to fit in remaining dimensions, to decrease the number of operations
        # in get_group_id()
        new_max_grid = [mg / g1 / g2 for mg, g1, g2 in zip(max_grid, grid1[0], grid1[1])]
        if len(new_max_grid) > 2 and product(new_max_grid[2:]) >= grid[2]:
            grid2 = self.get_rearranged_grid_1d([grid[2]], new_max_grid[2:])
            grid2 = [[1, 1] + grid2[0]]
        elif len(new_max_grid) > 1 and product(new_max_grid[1:]) >= grid[2]:
            grid2 = self.get_rearranged_grid_1d([grid[2]], new_max_grid[1:])
            grid2 = [[1] + grid2[0]]
        else:
            grid2 = self.get_rearranged_grid_1d([grid[2]], new_max_grid)

        return grid1 + grid2

    def get_rearranged_grid_1d(self, grid, max_grid):
        g = grid[0]
        if g <= max_grid[0]:
            return [[g] + [1] * (len(max_grid) - 1)]

        # for cases when max_grid was passed from higher dimension methods,
        # and there is no space left
        if max_grid[0] == 0:
            return [[1] + self.get_rearranged_grid_1d([g], max_grid[1:])[0]]

        # first check if we can split the number
        fs = factors(g)
        for f, div in reversed(fs):
            if f <= max_grid[0]:
                break

        if f != 1 and div <= product(max_grid[1:]):
            res = self.get_rearranged_grid_1d([div], max_grid[1:])
            return [[f] + res[0]]

        # fallback: will have some empty threads
        # picking factor equal to the power of 2 to make id calculations faster
        # Starting from low powers in order to minimize the number of resulting empty threads
        for p in xrange(1, log2(max_grid[-1]) + 1):
            f = 2 ** p
            remainder = min_blocks(g, f)
            if remainder <= product(max_grid[:-1]):
                res = self.get_rearranged_grid_1d([remainder], max_grid[:-1])
                return [res[0] + [f]]

        # fallback 2: couldn't find suitable 2**n factor, so using the maximum size
        f = max_grid[0]
        remainder = min_blocks(g, f)
        res = self.get_rearranged_grid_1d([remainder], max_grid[1:])
        return [[f] + res[0]]

    def render_vsize_funcs(self):
        return TEMPLATE.render(vs=self, product=product)

    def get_call_sizes(self):
        return tuple(self.k_global_size), tuple(self.k_local_size)