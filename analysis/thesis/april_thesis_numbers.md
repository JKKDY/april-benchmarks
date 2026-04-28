# APRIL thesis numbers

## Abstraction overhead

| label                   |   ns_per_interaction |   interactions_per_second | note                                                     |
|:------------------------|---------------------:|--------------------------:|:---------------------------------------------------------|
| APRIL AoS scalar        |             1.02202  |               9.78453e+08 | APRIL scalar AoS accessor path.                          |
| Handwritten AoS scalar  |             1.01876  |               9.81582e+08 | Comparable scalar AoS handwritten loop.                  |
| APRIL SoA scalar        |             1.18964  |               8.40587e+08 | APRIL scalar SoA accessor path.                          |
| Handwritten SoA scalar  |             1.09524  |               9.13038e+08 | Uses local accumulators; not a perfectly equal baseline. |
| APRIL SoA SIMD          |             0.340226 |               2.93922e+09 | APRIL vectorized SoA direct-sum path.                    |
| APRIL AoSoA SIMD        |             0.339221 |               2.94793e+09 | APRIL vectorized AoSoA direct-sum path.                  |
| Handwritten SoA 2D SIMD |             0.344393 |               2.90366e+09 | Explicit 2D SIMD rotation-sweep reference.               |
| Handwritten SoA 1D SIMD |             0.461186 |               2.16832e+09 | Broadcast-reduce SIMD reference.                         |

### Ratios

| label                                      |   ratio_value | note                                                              |
|:-------------------------------------------|--------------:|:------------------------------------------------------------------|
| APRIL AoS scalar / handwritten AoS scalar  |      1.0032   | Ratio < 1 means APRIL is faster; ratio > 1 means APRIL is slower. |
| APRIL SoA scalar / handwritten SoA scalar  |      1.08619  | Ratio < 1 means APRIL is faster; ratio > 1 means APRIL is slower. |
| APRIL SoA SIMD / handwritten SoA 2D SIMD   |      0.9879   | Ratio < 1 means APRIL is faster; ratio > 1 means APRIL is slower. |
| APRIL AoSoA SIMD / handwritten SoA 2D SIMD |      0.984982 | Ratio < 1 means APRIL is faster; ratio > 1 means APRIL is slower. |

## Force-kernel focus

| label                             | config       | category               |   ns_per_interaction |   interactions_per_second |
|:----------------------------------|:-------------|:-----------------------|---------------------:|--------------------------:|
| APRIL LinkedCells AoS scalar      | native       | linked_cells_scalar    |             3.35221  |               2.98311e+08 |
| APRIL LinkedCells SoA scalar      | native       | linked_cells_scalar    |             4.13496  |               2.4184e+08  |
| APRIL LinkedCells SoA SIMD        | native       | linked_cells_simd      |             1.12287  |               8.90573e+08 |
| APRIL LinkedCells AoSoA SIMD      | native       | linked_cells_simd      |             1.07982  |               9.26076e+08 |
| APRIL DirectSum SoA SIMD          | native       | direct_sum_simd        |             0.940596 |               1.06316e+09 |
| APRIL DirectSum AoSoA SIMD        | native       | direct_sum_simd        |             0.923501 |               1.08284e+09 |
| Manual Triangle SoA               | native       | manual_reference       |             0.976272 |               1.0243e+09  |
| Manual Triangle SoA explicit SIMD | native       | manual_reference       |             0.858287 |               1.16511e+09 |
| Manual absolute max perf          | native       | lower_bound_reference  |             0.682052 |               1.46616e+09 |
| Manual realistic vector read      | native       | manual_reference       |             1.73135  |               5.77585e+08 |
| NOVEC APRIL DirectSum AoS scalar  | native-novec | novec_scalar           |             3.28788  |               3.04147e+08 |
| NOVEC APRIL DirectSum SoA scalar  | native-novec | novec_scalar           |             4.07526  |               2.45383e+08 |
| NOVEC Manual Triangle AoS         | native-novec | novec_manual_reference |             1.72631  |               5.79271e+08 |
| NOVEC Manual Triangle SoA         | native-novec | novec_manual_reference |             0.998642 |               1.00136e+09 |

## APRIL strong scaling

|    dt |   n |   threads | executor           |   performance_mups |   speedup |   parallel_efficiency |   median_step_time_s |
|------:|----:|----------:|:-------------------|-------------------:|----------:|----------------------:|---------------------:|
| 1e-07 | 100 |         1 | OmpExecutor        |               3.15 |  1        |              1        |             0.317399 |
| 1e-07 | 100 |         2 | OmpExecutor        |               6.24 |  1.98095  |              0.990476 |             0.160156 |
| 1e-07 | 100 |         3 | OmpExecutor        |               9.3  |  2.95238  |              0.984127 |             0.107422 |
| 1e-07 | 100 |         4 | OmpExecutor        |              12.26 |  3.89206  |              0.973016 |             0.081559 |
| 1e-07 | 100 |         6 | OmpExecutor        |              18.15 |  5.7619   |              0.960317 |             0.055061 |
| 1e-07 | 100 |         8 | OmpExecutor        |              23.87 |  7.57778  |              0.947222 |             0.041875 |
| 1e-07 | 100 |        11 | OmpExecutor        |              32.18 | 10.2159   |              0.928716 |             0.031056 |
| 1e-07 | 100 |        16 | OmpExecutor        |              44.77 | 14.2127   |              0.888294 |             0.022325 |
| 1e-07 | 100 |        23 | OmpExecutor        |              60.43 | 19.1841   |              0.834092 |             0.016536 |
| 1e-07 | 100 |        32 | OmpExecutor        |              78.21 | 24.8286   |              0.775893 |             0.01276  |
| 1e-07 | 100 |        37 | OmpExecutor        |              84.99 | 26.981    |              0.729215 |             0.011644 |
| 1e-07 | 100 |        45 | OmpExecutor        |              94.51 | 30.0032   |              0.666737 |             0.010288 |
| 1e-07 | 100 |        50 | OmpExecutor        |              97.3  | 30.8889   |              0.617778 |             0.0099   |
| 1e-07 | 100 |        56 | OmpExecutor        |              99.58 | 31.6127   |              0.564512 |             0.009635 |
| 0.005 | 100 |         1 | NativeSpinExecutor |               2.65 |  1        |              1        |             0.378452 |
| 0.005 | 100 |         2 | NativeSpinExecutor |               4.97 |  1.87547  |              0.937736 |             0.201105 |
| 0.005 | 100 |         3 | NativeSpinExecutor |               7.36 |  2.77736  |              0.925786 |             0.136054 |
| 0.005 | 100 |         4 | NativeSpinExecutor |               9.5  |  3.58491  |              0.896226 |             0.10542  |
| 0.005 | 100 |         6 | NativeSpinExecutor |              13.82 |  5.21509  |              0.869182 |             0.072464 |
| 0.005 | 100 |         8 | NativeSpinExecutor |              17.75 |  6.69811  |              0.837264 |             0.05638  |
| 0.005 | 100 |        11 | NativeSpinExecutor |              23.14 |  8.73208  |              0.793825 |             0.043224 |
| 0.005 | 100 |        16 | NativeSpinExecutor |              30.73 | 11.5962   |              0.724764 |             0.032566 |
| 0.005 | 100 |        23 | NativeSpinExecutor |              40.35 | 15.2264   |              0.662018 |             0.024755 |
| 0.005 | 100 |        32 | NativeSpinExecutor |              49.6  | 18.717    |              0.584906 |             0.020121 |
| 0.005 | 100 |        37 | NativeSpinExecutor |              53.21 | 20.0792   |              0.542682 |             0.018749 |
| 0.005 | 100 |        45 | NativeSpinExecutor |              58.12 | 21.9321   |              0.487379 |             0.017194 |
| 0.005 | 100 |        50 | NativeSpinExecutor |              59.54 | 22.4679   |              0.449358 |             0.016737 |
| 0.005 | 100 |        56 | NativeSpinExecutor |              60.61 | 22.8717   |              0.408423 |             0.016459 |
| 0.005 | 100 |         1 | OmpExecutor        |               2.65 |  1        |              1        |             0.378471 |
| 0.005 | 100 |         1 | OmpExecutor        |               2.64 |  0.996226 |              0.996226 |             0.378828 |
| 0.005 | 100 |         1 | OmpExecutor        |               2.65 |  1        |              1        |             0.378391 |
| 0.005 | 160 |         1 | OmpExecutor        |               2.43 |  1        |              1        |             1.7073   |
| 0.005 | 100 |         2 | OmpExecutor        |               5.17 |  1.95094  |              0.975472 |             0.193745 |
| 0.005 | 100 |         2 | OmpExecutor        |               5.18 |  1.95472  |              0.977358 |             0.193369 |
| 0.005 | 100 |         2 | OmpExecutor        |               5.15 |  1.9434   |              0.971698 |             0.194533 |
| 0.005 | 160 |         2 | OmpExecutor        |               4.8  |  1.97531  |              0.987654 |             0.865974 |
| 0.005 | 100 |         3 | OmpExecutor        |               7.64 |  2.88302  |              0.961006 |             0.131063 |
| 0.005 | 100 |         3 | OmpExecutor        |               7.66 |  2.89057  |              0.963522 |             0.130732 |
| 0.005 | 100 |         3 | OmpExecutor        |               7.66 |  2.89057  |              0.963522 |             0.130557 |
| 0.005 | 160 |         3 | OmpExecutor        |               7.14 |  2.93827  |              0.979424 |             0.581668 |
| 0.005 | 100 |         4 | OmpExecutor        |              10.02 |  3.78113  |              0.945283 |             0.099888 |
| 0.005 | 100 |         4 | OmpExecutor        |               9.99 |  3.76981  |              0.942453 |             0.100168 |
| 0.005 | 100 |         4 | OmpExecutor        |               9.99 |  3.76981  |              0.942453 |             0.100274 |
| 0.005 | 160 |         4 | OmpExecutor        |               9.45 |  3.88889  |              0.972222 |             0.439966 |
| 0.005 | 100 |         6 | OmpExecutor        |              14.62 |  5.51698  |              0.919497 |             0.068521 |
| 0.005 | 100 |         6 | OmpExecutor        |              14.57 |  5.49811  |              0.916352 |             0.068728 |
| 0.005 | 100 |         6 | OmpExecutor        |              14.54 |  5.48679  |              0.914465 |             0.068825 |
| 0.005 | 160 |         6 | OmpExecutor        |              13.27 |  5.46091  |              0.910151 |             0.310724 |
| 0.005 | 100 |         8 | OmpExecutor        |              18.92 |  7.13962  |              0.892453 |             0.052841 |
| 0.005 | 100 |         8 | OmpExecutor        |              18.93 |  7.1434   |              0.892925 |             0.052907 |
| 0.005 | 100 |         8 | OmpExecutor        |              18.87 |  7.12075  |              0.890094 |             0.052996 |
| 0.005 | 160 |         8 | OmpExecutor        |              18.14 |  7.46502  |              0.933128 |             0.228592 |
| 0.005 | 100 |        11 | OmpExecutor        |              24.82 |  9.36604  |              0.851458 |             0.040335 |
| 0.005 | 100 |        11 | OmpExecutor        |              24.84 |  9.37358  |              0.852144 |             0.040294 |
| 0.005 | 100 |        11 | OmpExecutor        |              24.53 |  9.2566   |              0.841509 |             0.040856 |
| 0.005 | 160 |        11 | OmpExecutor        |              24.46 | 10.0658   |              0.915077 |             0.170362 |
| 0.005 | 100 |        16 | OmpExecutor        |              33.19 | 12.5245   |              0.782783 |             0.030117 |
| 0.005 | 100 |        16 | OmpExecutor        |              33.25 | 12.5472   |              0.784198 |             0.03003  |
| 0.005 | 100 |        16 | OmpExecutor        |              31.86 | 12.0226   |              0.751415 |             0.031114 |
| 0.005 | 160 |        16 | OmpExecutor        |              33.8  | 13.9095   |              0.869342 |             0.123501 |
| 0.005 | 100 |        23 | OmpExecutor        |              42.42 | 16.0075   |              0.69598  |             0.023495 |
| 0.005 | 100 |        23 | OmpExecutor        |              40.8  | 15.3962   |              0.669401 |             0.024524 |
| 0.005 | 100 |        23 | OmpExecutor        |              41.27 | 15.5736   |              0.677112 |             0.024185 |
| 0.005 | 160 |        23 | OmpExecutor        |              44.87 | 18.465    |              0.802827 |             0.093601 |
| 0.005 | 100 |        32 | OmpExecutor        |              47.1  | 17.7736   |              0.555425 |             0.021519 |
| 0.005 | 100 |        32 | OmpExecutor        |              51.43 | 19.4075   |              0.606486 |             0.019414 |
| 0.005 | 100 |        32 | OmpExecutor        |              49.48 | 18.6717   |              0.583491 |             0.020184 |
| 0.005 | 160 |        32 | OmpExecutor        |              55.85 | 22.9835   |              0.718236 |             0.07593  |
| 0.005 | 100 |        37 | OmpExecutor        |              54.46 | 20.5509   |              0.555431 |             0.018357 |
| 0.005 | 100 |        37 | OmpExecutor        |              54.25 | 20.4717   |              0.553289 |             0.018428 |
| 0.005 | 100 |        37 | OmpExecutor        |              51.94 | 19.6      |              0.52973  |             0.019251 |
| 0.005 | 160 |        37 | OmpExecutor        |              59.49 | 24.4815   |              0.661662 |             0.070756 |
| 0.005 | 100 |        45 | OmpExecutor        |              59    | 22.2642   |              0.494759 |             0.016872 |
| 0.005 | 100 |        45 | OmpExecutor        |              59.09 | 22.2981   |              0.495514 |             0.016873 |
| 0.005 | 100 |        45 | OmpExecutor        |              57.1  | 21.5472   |              0.478826 |             0.017461 |
| 0.005 | 160 |        45 | OmpExecutor        |              64.91 | 26.7119   |              0.593599 |             0.065961 |
| 0.005 | 100 |        50 | OmpExecutor        |              59.51 | 22.4566   |              0.449132 |             0.016791 |
| 0.005 | 100 |        50 | OmpExecutor        |              51.34 | 19.3736   |              0.387472 |             0.019491 |
| 0.005 | 100 |        50 | OmpExecutor        |              58.73 | 22.1623   |              0.443245 |             0.017027 |
| 0.005 | 160 |        50 | OmpExecutor        |              65.69 | 27.0329   |              0.540658 |             0.064605 |
| 0.005 | 100 |        56 | OmpExecutor        |              57.15 | 21.566    |              0.385108 |             0.017486 |
| 0.005 | 100 |        56 | OmpExecutor        |              49.69 | 18.7509   |              0.334838 |             0.020053 |
| 0.005 | 100 |        56 | OmpExecutor        |              57.83 | 21.8226   |              0.38969  |             0.017269 |
| 0.005 | 160 |        56 | OmpExecutor        |              64.03 | 26.3498   |              0.470532 |             0.06635  |
