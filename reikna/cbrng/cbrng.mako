<%def name="cbrng(kernel_declaration, counters, randoms)">
<%
    bijection = sampler.bijection
    randoms_per_call = sampler.randoms_per_call
%>

${kernel_declaration}
{
    VIRTUAL_SKIP_THREADS;

    const VSIZE_T idx = virtual_global_id(0);

    ${bijection.key_ctype} key = ${keygen.module}key_from_int(idx);

    ${bijection.counter_ctype} counter =
        ${counters.load_combined_idx(counters_slices)}(idx);

    ${bijection.module}STATE state = ${bijection.module}make_state(key, counter);

    ${sampler.module}RESULT result;
    for (VSIZE_T i = 0; i < ${batch // randoms_per_call}; i++)
    {
        result = ${sampler.module}sample(&state);
        %for j in range(randoms_per_call):
        ${randoms.store_combined_idx(randoms_slices)}(
            i * ${randoms_per_call} + ${j}, idx, result.v[${j}]);
        %endfor
    }
    %if batch % randoms_per_call != 0:
    result = ${sampler.module}sample(&state);
    %for j in range(batch % randoms_per_call):
    ${randoms.store_combined_idx(randoms_slices)}(
        ${batch - batch % randoms_per_call + j}, idx, result.v[${j}]);
    %endfor
    %endif

    ${bijection.counter_ctype} next_ctr = ${bijection.module}get_next_unused_counter(state);
    ${counters.store_combined_idx(counters_slices)}(idx, state.counter);
}
</%def>
