import tempfile
from pathlib import Path

import pytest

import ibis
import ibis.common.exceptions as com
import ibis.expr.datatypes as dt
from ibis.expr.window import window
from ibis.udf.vectorized import analytic, elementwise, reduction

pytestmark = pytest.mark.udf


@elementwise(input_type=[dt.double], output_type=dt.double)
def add_one(s):
    return s + 1


@analytic(input_type=[dt.double], output_type=dt.double)
def calc_zscore(s):
    return (s - s.mean()) / s.std()


@reduction(input_type=[dt.double], output_type=dt.double)
def calc_mean(s):
    return s.mean()


@elementwise(
    input_type=[dt.double],
    output_type=dt.Struct(['col1', 'col2'], [dt.double, dt.double]),
)
def add_one_struct(v):
    return v + 1, v + 2


@elementwise(
    input_type=[dt.double],
    output_type=dt.Struct(['double_col', 'col2'], [dt.double, dt.double]),
)
def overwrite_struct_elementwise(v):
    return v + 1, v + 2


@elementwise(
    input_type=[dt.double],
    output_type=dt.Struct(
        ['double_col', 'col2', 'float_col'], [dt.double, dt.double, dt.double]
    ),
)
def multiple_overwrite_struct_elementwise(v):
    return v + 1, v + 2, v + 3


@analytic(
    input_type=[dt.double, dt.double],
    output_type=dt.Struct(
        ['double_col', 'demean_weight'], [dt.double, dt.double]
    ),
)
def overwrite_struct_analytic(v, w):
    return v - v.mean(), w - w.mean()


@analytic(
    input_type=[dt.double, dt.double],
    output_type=dt.Struct(['demean', 'demean_weight'], [dt.double, dt.double]),
)
def demean_struct(v, w):
    return v - v.mean(), w - w.mean()


@reduction(
    input_type=[dt.double, dt.double],
    output_type=dt.Struct(['mean', 'mean_weight'], [dt.double, dt.double]),
)
def mean_struct(v, w):
    return v.mean(), w.mean()


@reduction(
    input_type=[dt.double, dt.double],
    output_type=dt.Struct(
        ['double_col', 'mean_weight'], [dt.double, dt.double]
    ),
)
def overwrite_struct_reduction(v, w):
    return v.mean(), w.mean()


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf(backend, alltypes, df):
    result = add_one(alltypes['double_col']).execute()
    expected = add_one.func(df['double_col'])
    backend.assert_series_equal(result, expected, check_names=False)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_mutate(backend, alltypes, df):
    expr = alltypes.mutate(incremented=add_one(alltypes['double_col']))
    result = expr.execute()

    expected = df.assign(incremented=add_one.func(df['double_col']))

    backend.assert_series_equal(result['incremented'], expected['incremented'])


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_analytic_udf(backend, alltypes, df):
    result = calc_zscore(alltypes['double_col']).execute()
    expected = calc_zscore.func(df['double_col'])
    backend.assert_series_equal(result, expected, check_names=False)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_analytic_udf_mutate(backend, alltypes, df):
    expr = alltypes.mutate(zscore=calc_zscore(alltypes['double_col']))
    result = expr.execute()

    expected = df.assign(zscore=calc_zscore.func(df['double_col']))

    backend.assert_series_equal(result['zscore'], expected['zscore'])


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_reduction_udf(backend, alltypes, df):
    result = calc_mean(alltypes['double_col']).execute()
    expected = df['double_col'].agg(calc_mean.func)
    assert result == expected


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_output_type_in_list_invalid(backend, alltypes, df):
    # Test that an error is raised if UDF output type is wrapped in a list

    with pytest.raises(
        com.IbisTypeError,
        match="The output type of a UDF must be a single datatype.",
    ):

        @elementwise(input_type=[dt.double], output_type=[dt.double])
        def add_one(s):
            return s + 1


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_valid_kwargs(backend, alltypes, df):
    # Test different forms of UDF definition with keyword arguments

    @elementwise(input_type=[dt.double], output_type=dt.double)
    def foo1(v):
        # Basic UDF with kwargs
        return v + 1

    @elementwise(input_type=[dt.double], output_type=dt.double)
    def foo2(v, *, amount):
        # UDF with keyword only arguments
        return v + amount

    @elementwise(input_type=[dt.double], output_type=dt.double)
    def foo3(v, **kwargs):
        # UDF with kwargs
        return v + kwargs.get('amount', 1)

    result = alltypes.mutate(
        v1=foo1(alltypes['double_col']),
        v2=foo2(alltypes['double_col'], amount=1),
        v3=foo2(alltypes['double_col'], amount=2),
        v4=foo3(alltypes['double_col']),
        v5=foo3(alltypes['double_col'], amount=2),
        v6=foo3(alltypes['double_col'], amount=3),
    ).execute()

    expected = df.assign(
        v1=df['double_col'] + 1,
        v2=df['double_col'] + 1,
        v3=df['double_col'] + 2,
        v4=df['double_col'] + 1,
        v5=df['double_col'] + 2,
        v6=df['double_col'] + 3,
    )

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_valid_args(backend, alltypes, df):
    # Test different forms of UDF definition with *args

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo1(*args):
        return args[0] + args[1]

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo2(v, *args):
        return v + args[0]

    result = alltypes.mutate(
        v1=foo1(alltypes['double_col'], alltypes['int_col']),
        v2=foo2(alltypes['double_col'], alltypes['int_col']),
    ).execute()

    expected = df.assign(
        v1=df['double_col'] + df['int_col'],
        v2=df['double_col'] + df['int_col'],
    )

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_valid_args_and_kwargs(backend, alltypes, df):
    # Test UDFs with both *args and keyword arguments

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo1(*args, amount):
        # UDF with *args and a keyword-only argument
        return args[0] + args[1] + amount

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo2(*args, **kwargs):
        # UDF with *args and **kwargs
        return args[0] + args[1] + kwargs.get('amount', 1)

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo3(v, *args, amount):
        # UDF with an explicit positional argument, *args, and a keyword-only
        # argument
        return v + args[0] + amount

    @elementwise(input_type=[dt.double, dt.int32], output_type=dt.double)
    def foo4(v, *args, **kwargs):
        # UDF with an explicit positional argument, *args, and **kwargs
        return v + args[0] + kwargs.get('amount', 1)

    result = alltypes.mutate(
        v1=foo1(alltypes['double_col'], alltypes['int_col'], amount=2),
        v2=foo2(alltypes['double_col'], alltypes['int_col'], amount=2),
        v3=foo3(alltypes['double_col'], alltypes['int_col'], amount=2),
        v4=foo4(alltypes['double_col'], alltypes['int_col'], amount=2),
    ).execute()

    expected = df.assign(
        v1=df['double_col'] + df['int_col'] + 2,
        v2=df['double_col'] + df['int_col'] + 2,
        v3=df['double_col'] + df['int_col'] + 2,
        v4=df['double_col'] + df['int_col'] + 2,
    )

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_invalid_kwargs(backend, alltypes):
    # Test that defining a UDF with a non-column argument that is not a
    # keyword argument raises an error

    with pytest.raises(TypeError, match=".*must be defined as keyword only.*"):

        @elementwise(input_type=[dt.double], output_type=dt.double)
        def foo1(v, amount):
            return v + 1


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_destruct(backend, alltypes):
    result = alltypes.mutate(
        add_one_struct(alltypes['double_col']).destructure()
    ).execute()

    expected = alltypes.mutate(
        col1=alltypes['double_col'] + 1, col2=alltypes['double_col'] + 2,
    ).execute()

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_overwrite_destruct(backend, alltypes):
    result = alltypes.mutate(
        overwrite_struct_elementwise(alltypes['double_col']).destructure()
    ).execute()

    expected = alltypes.mutate(
        double_col=alltypes['double_col'] + 1, col2=alltypes['double_col'] + 2,
    ).execute()

    # TODO issue #2649
    # Due to a known limitation with how we treat DestructColumn
    # in assignments, the ordering of op.selections may not exactly
    # correspond with the column ordering we want (i.e. all new columns
    # should appear at the end, but currently they are materialized
    # directly after those overwritten columns).
    backend.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_overwrite_destruct_and_assign(backend, alltypes):
    result = (
        alltypes.mutate(
            overwrite_struct_elementwise(alltypes['double_col']).destructure()
        )
        .mutate(col3=alltypes['int_col'] * 3)
        .execute()
    )

    expected = alltypes.mutate(
        double_col=alltypes['double_col'] + 1,
        col2=alltypes['double_col'] + 2,
        col3=alltypes['int_col'] * 3,
    ).execute()

    # TODO issue #2649
    # Due to a known limitation with how we treat DestructColumn
    # in assignments, the ordering of op.selections may not exactly
    # correspond with the column ordering we want (i.e. all new columns
    # should appear at the end, but currently they are materialized
    # directly after those overwritten columns).
    backend.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
@pytest.mark.min_spark_version('3.1')
def test_elementwise_udf_destruct_exact_once(backend, alltypes):
    with tempfile.TemporaryDirectory() as tempdir:

        @elementwise(
            input_type=[dt.double],
            output_type=dt.Struct(['col1', 'col2'], [dt.double, dt.double]),
        )
        def add_one_struct_exact_once(v):
            key = v.iloc[0]
            path = Path(f"{tempdir}/{key}")
            assert not path.exists()
            path.touch()
            return v + 1, v + 2

        result = alltypes.mutate(
            add_one_struct_exact_once(alltypes['index']).destructure()
        )

        result = result.execute()

        assert len(result) > 0


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_multiple_overwrite_destruct(backend, alltypes):
    result = alltypes.mutate(
        multiple_overwrite_struct_elementwise(
            alltypes['double_col']
        ).destructure()
    ).execute()

    expected = alltypes.mutate(
        double_col=alltypes['double_col'] + 1,
        col2=alltypes['double_col'] + 2,
        float_col=alltypes['double_col'] + 3,
    ).execute()

    # TODO issue #2649
    # Due to a known limitation with how we treat DestructColumn
    # in assignments, the ordering of op.selections may not exactly
    # correspond with the column ordering we want (i.e. all new columns
    # should appear at the end, but currently they are materialized
    # directly after those overwritten columns).
    backend.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_named_destruct(backend, alltypes):
    """Test error when assigning name to a destruct column."""

    with pytest.raises(
        com.ExpressionError, match=r".*Cannot name a destruct.*"
    ):
        alltypes.mutate(
            new_struct=add_one_struct(alltypes['double_col']).destructure()
        )


@pytest.mark.only_on_backends(['pyspark'])
@pytest.mark.xfail_unsupported
def test_elementwise_udf_struct(backend, alltypes):
    result = alltypes.mutate(
        new_col=add_one_struct(alltypes['double_col'])
    ).execute()
    result = result.assign(
        col1=result['new_col'].apply(lambda x: x[0]),
        col2=result['new_col'].apply(lambda x: x[1]),
    )
    result = result.drop('new_col', axis=1)
    expected = alltypes.mutate(
        col1=alltypes['double_col'] + 1, col2=alltypes['double_col'] + 2,
    ).execute()

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
def test_analytic_udf_destruct(backend, alltypes):
    w = window(preceding=None, following=None, group_by='year')

    result = alltypes.mutate(
        demean_struct(alltypes['double_col'], alltypes['int_col'])
        .over(w)
        .destructure()
    ).execute()

    expected = alltypes.mutate(
        demean=alltypes['double_col'] - alltypes['double_col'].mean().over(w),
        demean_weight=alltypes['int_col'] - alltypes['int_col'].mean().over(w),
    ).execute()

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_analytic_udf_destruct_overwrite(backend, alltypes):
    w = window(preceding=None, following=None, group_by='year')

    result = alltypes.mutate(
        overwrite_struct_analytic(alltypes['double_col'], alltypes['int_col'])
        .over(w)
        .destructure()
    ).execute()

    expected = alltypes.mutate(
        double_col=alltypes['double_col']
        - alltypes['double_col'].mean().over(w),
        demean_weight=alltypes['int_col'] - alltypes['int_col'].mean().over(w),
    ).execute()

    # TODO issue #2649
    # Due to a known limitation with how we treat DestructColumn
    # in assignments, the ordering of op.selections may not exactly
    # correspond with the column ordering we want (i.e. all new columns
    # should appear at the end, but currently they are materialized
    # directly after those overwritten columns).
    backend.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.only_on_backends(['pandas'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
def test_reduction_udf_destruct_groupby(backend, alltypes):
    result = (
        alltypes.groupby('year')
        .aggregate(
            mean_struct(
                alltypes['double_col'], alltypes['int_col']
            ).destructure()
        )
        .execute()
    )

    expected = (
        alltypes.groupby('year')
        .aggregate(
            mean=alltypes['double_col'].mean(),
            mean_weight=alltypes['int_col'].mean(),
        )
        .execute()
    )

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
def test_reduction_udf_destruct_no_groupby(backend, alltypes):
    result = alltypes.aggregate(
        mean_struct(alltypes['double_col'], alltypes['int_col']).destructure()
    ).execute()

    expected = alltypes.aggregate(
        mean=alltypes['double_col'].mean(),
        mean_weight=alltypes['int_col'].mean(),
    ).execute()

    backend.assert_frame_equal(result, expected)


@pytest.mark.only_on_backends(['pandas', 'pyspark'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
@pytest.mark.xfail_unsupported
def test_reduction_udf_destruct_no_groupby_overwrite(backend, alltypes):
    result = alltypes.aggregate(
        overwrite_struct_reduction(
            alltypes['double_col'], alltypes['int_col']
        ).destructure()
    ).execute()

    expected = alltypes.aggregate(
        double_col=alltypes['double_col'].mean(),
        mean_weight=alltypes['int_col'].mean(),
    ).execute()
    # TODO issue #2649
    # Due to a known limitation with how we treat DestructColumn
    # in assignments, the ordering of op.selections may not exactly
    # correspond with the column ordering we want (i.e. all new columns
    # should appear at the end, but currently they are materialized
    # directly after those overwritten columns).
    backend.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.only_on_backends(['pandas'])
# TODO - udf - #2553
@pytest.mark.xfail_backends(['dask'])
def test_reduction_udf_destruct_window(backend, alltypes):
    win = window(
        preceding=ibis.interval(hours=2),
        following=0,
        group_by='year',
        order_by='timestamp_col',
    )

    result = alltypes.mutate(
        mean_struct(alltypes['double_col'], alltypes['int_col'])
        .over(win)
        .destructure()
    ).execute()

    expected = alltypes.mutate(
        mean=alltypes['double_col'].mean().over(win),
        mean_weight=alltypes['int_col'].mean().over(win),
    ).execute()

    backend.assert_frame_equal(result, expected)
