import numpy
import pytest

from helpers import *

from tigger.elementwise import Elementwise
import tigger.cluda.dtypes as dtypes

def test_errors(ctx):

    elw = Elementwise(ctx,
        """
        ${input.ctype} a1 = ${input.load}(idx);
        ${input.ctype} a2 = ${input.load}(idx + size);
        ${output.store}(idx, a1 + a2 + ${param});
        """,
        (['output'], ['input'], ['param']))

    N = 1000
    a = get_test_array(N * 2, numpy.float32)
    a_dev = ctx.to_device(a)
    b_dev = ctx.allocate(N, numpy.float32)
    param = 1

    elw.prepare(
        output_dtype=numpy.float32, input_dtype=numpy.float32,
        param_dtype=numpy.float32, size=N)
    elw(b_dev, a_dev, param)
    assert diff_is_negligible(ctx.from_device(b_dev), a[:N] + a[N:] + param)

    elw.prepare_for(b_dev, a_dev, numpy.float32(param))
    elw(b_dev, a_dev, param)
    assert diff_is_negligible(ctx.from_device(b_dev), a[:N] + a[N:] + param)