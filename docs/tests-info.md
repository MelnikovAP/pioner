# PIONER test suite - canonical index

**285 collected test cases** across **16 test files** (272 test functions;
parametrized functions expand to several cases each). This file is the **single
source of truth for the test count** - other docs link here instead of
repeating the number.

Run the suite / regenerate the numbers:

```bash
PYTHONPATH=src .venv/bin/pytest -q                              # full run (~55 s, mock backend)
PYTHONPATH=src .venv/bin/pytest tests/ --collect-only -q | grep -c ::   # 285 (collected cases)
```

> Maintenance: this is a hand-maintained list and rots fast. When you add,
> rename, or delete a test, update this file in the same change - add/fix the
> numbered line, and fix both the per-file counts and the totals in this header.
> The "N functions / M cases" split differs only for parametrized files.

Numbering is continuous (1..272) over the files in pytest collection
(alphabetical) order. Parametrized functions are listed once with their case
count in parentheses.

---

## tests/test_acquisition_provider.py - 13 functions / 17 cases

1. `test_default_for_missing` - parser returns persistent mode for null/empty strings.
2. `test_default_for_unknown` - parser returns persistent mode for unknown input.
3. `test_known_values` - parser returns correct modes for "persistent" and "per_experiment".
4. `test_whitespace_and_case_tolerant` - parser accepts whitespace and case variations.
5. `test_creates_persistent_by_default` - factory creates PersistentAIProvider when mode unspecified.
6. `test_creates_per_experiment_when_requested` - factory creates PerExperimentAIProvider when requested.
7. `test_falls_back_on_unknown_string` - factory falls back to persistent for an unknown string.
8. `test_peek_returns_2d_with_six_channels` - peek returns a 2D array, six channels, bounded rows (parametrized, 2 cases).
9. `test_read_new_returns_data_then_diminishes` - read_new returns initial data, then smaller deltas (parametrized, 2 cases).
10. `test_independent_consumers` - independent consumers receive comparable initial batches (parametrized, 2 cases).
11. `test_on_disconnect_is_idempotent` - disconnect is idempotent, returns empty arrays (parametrized, 2 cases).
12. `test_arm_keeps_ai_running` - persistent provider keeps AI running across arm/end hooks.
13. `test_arm_stops_monitoring_end_restarts` - per-experiment provider pauses AI on arm, resumes on end.

## tests/test_acquisition_ring.py - 8 functions / 8 cases

14. `test_peek_last_returns_at_most_n_samples` - peek returns at most N rows and never advances cursors.
15. `test_peek_last_zero_returns_empty` - peek with zero returns an empty 2D array.
16. `test_peek_last_more_than_available_returns_what_exists` - peek with an oversized N returns available data.
17. `test_read_new_first_call_returns_current_ring` - first read_new for a consumer returns the current ring.
18. `test_read_new_advances_cursor` - subsequent read_new returns only new samples.
19. `test_read_new_independent_cursors` - two consumers keep independent cursors.
20. `test_reset_ring_cursor` - reset drops the per-consumer cursor and rejoins at head.
21. `test_start_ring_buffer_raises_if_scan_never_runs` - ring start fails fast when the AI scan never reaches RUNNING.

## tests/test_apply_calibration.py - 12 functions / 12 cases

22. `test_uref_is_tiled_for_continuous_iso_buffer` - a 1 s AO buffer tiled to a 3 s AI capture yields a 3 s Uref.
23. `test_uref_is_tiled_for_dc_iso_single_sample_profile` - a DC iso single-sample profile holds constant in Uref.
24. `test_thtr_is_nan_when_heater_current_is_zero` - zero current yields NaN Thtr, not a sentinel.
25. `test_thtr_is_finite_when_heater_current_is_present` - non-zero current produces a finite Thtr.
26. `test_rhtr_units_are_ohms_with_si_calibration` - the SI-calibration formula yields a physically plausible Thtr range.
27. `test_apply_calibration_preserves_length_and_drops_raw_columns` - output length preserved, raw columns dropped.
28. `test_apply_calibration_handles_empty_input` - empty input produces empty output.
29. `test_apply_calibration_scales_channels_once_and_leaves_input_untouched` - channels scaled once, input frame untouched.
30. `test_kamp_divide_applies_and_guards` - _kamp_divide divides amplitude by kamp(Thtr) and NaNs uncorrectable samples.
31. `test_kamp_divide_nans_nonpositive_gain` - non-positive kamp(Thtr) marks samples NaN.
32. `test_lockin_reference_selects_ch0_only_when_opted_in` - _lockin_reference returns AI ch0 only when measured-reference is opted in.
33. `test_heater_resistance_all_nan_when_channels_absent` - absent heater channels yield all-NaN resistance.

## tests/test_back_settings.py - 23 functions / 23 cases

34. `test_default_settings_hardware_trigger_off` - committed defaults keep the hardware trigger off.
35. `test_hardware_trigger_true_round_trips` - HardwareTrigger True persists through settings.
36. `test_hardware_trigger_false_round_trips` - HardwareTrigger False persists through settings.
37. `test_hardware_trigger_missing_defaults_off` - a legacy file without the field defaults to False.
38. `test_default_per_mode_rates` - committed defaults split sample rates by mode.
39. `test_bare_int_rate_back_compat` - a scalar sample rate applies to every mode.
40. `test_rate_map_partial_falls_back_to_default` - missing per-mode rates inherit the Default key.
41. `test_rate_map_without_default_is_invalid` - a sample-rate map without Default raises.
42. `test_rate_bool_is_invalid` - a boolean sample-rate value raises.
43. `test_default_limits` - committed defaults define per-mode temperature and rate limits.
44. `test_limits_missing_block_defaults` - a missing Limits block falls back to built-in defaults.
45. `test_limits_flat_block_applies_to_all_modes` - a non per-mode Limits block applies to all modes.
46. `test_parse_experiment_limits_custom` - custom temperature and rate limits parse correctly.
47. `test_parse_experiment_limits_by_mode_partial` - per-mode limits with absent modes use defaults.
48. `test_parse_experiment_limits_rejects_non_number` - non-numeric limit values raise.
49. `test_front_settings_round_trips_limits_block` - GUI save preserves the optional Limits block.
50. `test_front_settings_omits_measured_reference_when_absent` - GUI save omits MeasuredReference when absent.
51. `test_front_settings_round_trips_measured_reference` - GUI save preserves Modulation.MeasuredReference.
52. `test_rate_map_accepts_capitalized_keys` - capitalized mode keys normalize to lowercase.
53. `test_limits_accepts_capitalized_mode_keys` - capitalized mode keys in limits parse to lowercase.
54. `test_chip_presence_strategy_camelcase` - chip-detection strategy names normalize from CamelCase.
55. `test_acquisition_mode_camelcase` - acquisition-mode CamelCase values normalize to snake_case.
56. `test_get_str_returns_valid_json` - get_str emits valid JSON (P2-6 regression; stored as HDF5 run metadata).

## tests/test_calibration.py - 23 functions / 23 cases

57. `test_reads_default_calibration_from_package_rel_path` - bundled defaults resolve via DEFAULT_CALIBRATION_FILE_REL_PATH.
58. `test_default_calibration_is_identity` - the default calibration is identity and round-trips.
59. `test_temperature_to_voltage_logs_when_clamping` - the defense-in-depth clamp logs a warning.
60. `test_temperature_to_voltage_clamps_to_safe_voltage` - out-of-range temperature clamps to safe_voltage.
61. `test_temperature_to_voltage_handles_array_input` - array input round-trips within one grid step.
62. `test_calibration_round_trip` - write/read persists comment and Hardware fields.
63. `test_calibration_rejects_wrong_extension` - a non-.json file extension is rejected.
64. `test_calibration_rejects_missing_block` - JSON missing the Calibration coeff block is rejected.
65. `test_temperature_to_voltage_empty_input` - empty input returns empty output.
66. `test_temperature_to_voltage_non_monotonic_raises` - an overall non-monotonic trend raises ValueError.
67. `test_production_calibration_polynomial_inverts` - real chip calibration recovers voltages within a grid step.
68. `test_default_calibration_pins_identity_constants` - bundled defaults have identity coefficients.
69. `test_kamp_polynomial_scalar_and_array` - kamp(T) works for scalars and arrays.
70. `test_amplitude_correction_enabled_round_trips` - the amplitude-correction enabled flag persists.
71. `test_solve_rhcorr_converges_identity_polynomial` - an identity Thtr poly converges to the target correction.
72. `test_solve_rhcorr_converges_production_polynomial` - a realistic quadratic Thtr poly converges.
73. `test_solve_rhcorr_refines_from_corr_start` - iteration refines an existing correction rather than resetting.
74. `test_solve_rhcorr_diverges_resets_to_zero` - a divergent polynomial resets the correction to zero.
75. `test_solve_rhcorr_rejects_zero_or_nonfinite_resistance` - no correction when heater current is undefined.
76. `test_compute_rhcorr_mutates_the_right_field` - compute_rhcorr stores into thtrcorr or thtrdcorr.
77. `test_classify_heater_resistance` - classification returns ok/broken/shorted/unknown.
78. `test_heater_threshold_round_trips` - heater thresholds persist and default correctly.
79. `test_read_malformed_calibration_raises_clear_error` - a malformed calibration file raises a clear ValueError.

## tests/test_chip_presence.py - 10 functions / 10 cases

80. `test_channel_metrics_basic` - channel_metrics computes mean/min/max/peak-to-peak/std.
81. `test_presence_metrics_maps_channels_by_column_order` - presence_metrics maps window columns to channels.
82. `test_presence_metrics_empty_window` - presence_metrics returns an empty dict for an empty window.
83. `test_detect_band` - the band strategy detects presence when the mean is within the band.
84. `test_detect_abs_level` - the abs_level strategy detects presence when |mean| is below threshold.
85. `test_detect_variance` - the variance strategy detects presence when std is below threshold.
86. `test_detect_unknown_strategy_raises` - detect raises ValueError for an unknown strategy.
87. `test_detect_channel_not_in_scan` - detect returns False with a reason when the channel is absent.
88. `test_presence_report_structure` - presence_report builds an available/channel/verdicts/metrics dict.
89. `test_presence_report_empty_window` - presence_report marks an empty window unavailable, metrics empty.

## tests/test_device_controller.py - 41 functions / 43 cases

90. `test_report_unavailable_when_heater_not_powered` - heater-health report unavailable when not powered.
91. `test_report_previews_correction_without_mutating` - preview shows a correction without mutating state.
92. `test_apply_persists_and_mutates` - apply persists the correction and mutates the calibration.
93. `test_unknown_when_not_powered` - unknown verdict when the heater is not powered.
94. `test_unknown_when_heater_channels_absent` - unknown verdict when heater channels are absent.
95. `test_classifies_powered_window` - classifies a powered window by resistance (parametrized, 3 cases).
96. `test_unknown_on_idle_noise` - an ADC-noise-only (cold heater) window yields "unknown", not a verdict from noise.
97. `test_report_available_on_live_stream` - report available with all strategies on a live stream.
98. `test_chip_present_none_when_disabled` - chip_present returns None when disabled.
99. `test_chip_present_when_enabled` - chip_present responds to the enabled config.
100. `test_connects_and_streams` - connection and streaming produce valid data.
101. `test_disconnect_is_idempotent` - a second disconnect does not raise.
102. `test_ai_sample_rate_reported` - the AI sample rate is reported positive.
103. `test_reports_mock_backend` - the controller reports the mock backend.
104. `test_set_and_get` - sample-rate set and get.
105. `test_reset_restores_file_value` - reset restores the original file sample rate.
106. `test_rate_change_keeps_stream_alive` - the stream stays active during a rate change.
107. `test_rate_for_mode_uses_per_mode_map` - mode-rate lookup returns the correct values.
108. `test_arm_applies_mode_rate` - arm switches to the mode's configured rate.
109. `test_fast_run_restores_pre_fast_rate` - a run restores the rate active before fast.
110. `test_override_mode_rate_is_used_on_arm` - an override rate is applied on the next arm.
111. `test_override_rejects_odd_rate` - override rejects odd sample rates.
112. `test_override_rejects_sub_nyquist_rate` - override rejects sub-Nyquist rates.
113. `test_default_calibration_loaded_on_connect` - the default calibration is loaded on connect.
114. `test_arm_run_fast_heat_writes_result` - a fast-heat run writes a result with engineering columns.
115. `test_run_without_arm_returns_none` - run without arm returns None.
116. `test_stream_resumes_after_experiment` - the stream resumes after the experiment completes.
117. `test_slow_run_streams_off_ring_and_writes_paths` - a slow run streams off-ring and writes two files.
118. `test_slow_run_stop_aborts_and_zeroes` - a slow-run stop aborts with the heater zeroed.
119. `test_iso_finite_run_streams_off_ring_and_writes_paths` - an iso finite run streams off-ring with constant Uref.
120. `test_iso_finite_run_zeroes_heater_on_completion` - a completed timed iso run zeroes the heater and keeps the live stream up.
121. `test_iso_run_streams_during_run` - an iso run produces samples while running.
122. `test_start_iso_hold_is_nonblocking_and_holds` - iso hold returns non-blocking and holds AO.
123. `test_start_iso_hold_requires_armed_iso` - start_iso_hold raises without an armed iso.
124. `test_stop_run_zeroes_heater_after_hold` - stop_run zeroes the heater after a hold.
125. `test_disconnect_zeroes_heater_after_hold` - disconnect zeroes the heater after a hold.
126. `test_streaming_run_zeroes_heater_on_exception` - an exception mid streaming-run zeroes the heater (no latched DAC).
127. `test_ai_sample_rate_prefers_actual_ring_rate` - the time-axis/demod rate is the driver-reported actual ring rate, not the nominal.
128. `test_ring_worker_death_is_visible` - a crashed ring worker flips is_streaming() False and stops serving stale data.
129. `test_override_rate_rejects_aggregate_overflow` - rates over the board's 1 MS/s aggregate (rate x channels) are rejected.
130. `test_atexit_backstop_registration_and_zero` - connect registers an atexit AO-zero hook; disconnect removes it; the hook zeroes AO.

## tests/test_disk_recorder.py - 7 functions / 7 cases

131. `test_records_baseline_and_run_with_mark` - the recorder captures baseline and run, mark at the boundary.
132. `test_start_primes_cursor_and_drops_backlog` - start primes the cursor and discards pre-arm backlog.
133. `test_mark_index_minus_one_when_never_marked` - mark_index is sentinel -1 when never marked.
134. `test_stop_without_data_writes_empty_file` - stop with no data writes an empty file (no raw_ai dataset).
135. `test_double_start_is_ignored` - a double start is a no-op and preserves is_recording.
136. `test_chunk_order_preserved_across_many_feeds` - chunk order is preserved across many feeds.
137. `test_periodic_flush_fires_during_recording` - drains flush the HDF5 file periodically (crash-survivable capture).

## tests/test_finalize_recording.py - 8 functions / 8 cases

138. `test_finalize_writes_separate_calibrated_file` - finalize writes a separate calibrated file and keeps the raw.
139. `test_finalize_chunked_matches_whole_frame` - block-by-block finalize equals a whole-frame apply_calibration.
140. `test_finalize_lockin_columns_with_modulation` - finalize writes lockin amp/phase/valid columns with modulation.
141. `test_finalize_program_offset_marks_baseline_uref_nan` - rows before program_offset get a NaN-Uref baseline.
142. `test_read_calibrated_decimation` - read_calibrated_h5 decimation: step, max_points, column subset.
143. `test_finalize_tile_profile_iso_vs_slice` - tile_profile True tiles the profile; False slices and NaNs past end.
144. `test_finalize_rejects_same_path` - finalize raises ValueError when input and output paths are identical.
145. `test_finalize_empty_raw_returns_none` - finalize returns None for an empty raw file.

## tests/test_logging_setup.py - 5 functions / 5 cases

146. `test_creates_session_file_and_writes` - configure_logging creates the session file and writes messages.
147. `test_filename_is_filesystem_safe` - session_log_filename is filesystem-safe (no colons).
148. `test_idempotent_no_duplicate_handlers` - configure_logging is idempotent, swapping handlers rather than stacking.
149. `test_console_handler_optional` - console=True adds both a FileHandler and a StreamHandler.
150. `test_creates_missing_log_dir` - configure_logging creates a missing log directory.

## tests/test_main_window.py - 35 functions / 42 cases

151. `test_local_connect_error_text` - maps connection-failure error messages (parametrized, 4 cases).
152. `test_local_mock_connect_sets_status_and_enables` - mock connect sets status, enables controls, confirms rate.
153. `test_disconnect_resets_status` - disconnect clears the controller, resets status, disables controls.
154. `test_fmt_blanks_none_and_nan` - the formatter blanks None/NaN but shows regular numbers.
155. `test_thtr_blanked_when_idle` - heater temperature blanks when idle while others still show.
156. `test_thtr_shown_when_driven` - heater temperature displays when actively driven.
157. `test_iso_eternal_hold_drives_and_marks` - an eternal hold arms the program and marks the heater driven.
158. `test_iso_off_zeroes_and_blanks` - Off arms 0 V and blanks the heater-driven state.
159. `test_iso_off_during_run_acts_as_stop` - Off during a run calls stop, not re-arm.
160. `test_iso_timed_launches_worker_and_resets_on_finish` - a timed program launches a worker and resets on finish.
161. `test_iso_set_without_backend_warns` - Set without a backend shows an error.
162. `test_iso_set_without_rate_confirmed_warns` - Set without a confirmed rate warns and does not arm.
163. `test_segment_mode_default_and_toggle_visibility` - the segments editor is default; the radio toggles visibility.
164. `test_segment_widgets_hidden_for_iso` - segment UI is hidden for iso, visible otherwise.
165. `test_segment_builder_converts_rate_to_duration` - heat/iso/cool segments convert to time/temp tables.
166. `test_segment_builder_nonzero_start` - cooling from a non-zero start builds correct tables.
167. `test_segment_builder_invalid_returns_none_with_warning` - invalid segments return None with an error (parametrized, 5 cases).
168. `test_segment_builder_bad_start_temp_warns` - a non-numeric start temp shows an error and returns None.
169. `test_segment_builder_delegates_to_core_validation` - invalid segment logic is rejected by core validation.
170. `test_fh_arm_segment_mode_arms_converted_program` - Fast mode arms the converted segment program.
171. `test_fh_arm_raw_mode_still_works` - raw-points mode still arms with time-scale conversion.
172. `test_arm_unsafe_voltage_blocks_and_counts` - unsafe voltage raises SafeVoltageError, warns, and counts a stat.
173. `test_check_chip_without_backend_warns` - a chip check without a backend shows an error.
174. `test_check_chip_shows_report` - the chip-presence check displays strategies and verdicts.
175. `test_check_heater_without_backend_warns` - a heater check without a backend shows an error.
176. `test_check_heater_shows_report` - the heater-health check displays a report and increments a stat.
177. `test_rhcorr_without_backend_warns` - R-correction without a backend shows an error.
178. `test_rhcorr_unavailable_shows_reason` - an unavailable R-correction shows a reason and does not apply.
179. `test_rhcorr_preview_confirm_applies` - a confirmed R-correction preview applies and shows the result.
180. `test_rhcorr_preview_cancel_does_not_apply` - a cancelled R-correction preview does not apply.
181. `test_rhcorr_diverged_warns_and_does_not_apply` - a diverged R-correction warns and does not apply.
182. `test_ui_action_logs_info_and_counts` - a Stop action logs at INFO and increments statistics.
183. `test_scope_change_logged_at_debug_not_info` - scope changes log at DEBUG, not INFO.
184. `test_close_logs_session_stats_summary` - window close logs the session-stats summary at INFO.
185. `test_fh_arm_raw_empty_table_warns` - an empty raw table shows an error and does not arm.

## tests/test_mock_uldaq.py - 5 functions / 5 cases

186. `test_lifecycle` - the device lifecycle connects and disconnects.
187. `test_create_float_buffer_shape` - float-buffer creation returns the correct list shape.
188. `test_ai_scan_progresses_and_stops` - an AI scan progresses and stops via a stop request.
189. `test_ai_buffer_is_shared_not_copied` - the AI buffer list mutates in place (shared object).
190. `test_ao_iso_voltage` - an AO iso voltage set returns the expected value.

## tests/test_modes_e2e.py - 51 functions / 51 cases

191. `test_fast_mode_no_point_loss` - FastHeat loses no samples over a one-second run.
192. `test_slow_mode_produces_lockin_columns` - SlowMode produces lock-in amplitude and phase columns.
193. `test_slow_mode_amplitude_correction_divides_reported_amplitude` - amplitude correction divides the reported amplitude.
194. `test_slow_mode_measured_reference_runs_and_produces_phase` - SlowMode with a measured reference produces a phase.
195. `test_arm_blocks_raw_volt_over_safe_voltage` - arm rejects heater programs over safe voltage.
196. `test_arm_blocks_temp_over_chip_ceiling` - arm rejects temperatures over the chip ceiling.
197. `test_arm_blocks_modulation_peak_over_safe_voltage` - arm rejects DC+AC peaks over safe voltage.
198. `test_arm_accepts_program_within_safe_voltage` - arm accepts programs within safe voltage.
199. `test_iso_mode_streams_into_dataframe` - IsoMode produces the expected sample count.
200. `test_iso_mode_with_modulation_emits_fft_attrs_and_warns_on_non_seamless` - iso AC logs a non-seamless warning and emits FFT attrs.
201. `test_iso_ac_with_hardware_trigger_runs_clean` - iso AC with a hardware trigger completes cleanly.
202. `test_fast_mode_with_hardware_trigger_runs_clean` - FastHeat with a hardware trigger produces a full frame.
203. `test_ao_set_rejects_out_of_range_voltage` - a direct AO set rejects out-of-range voltage.
204. `test_iso_dc_temp_program_goes_through_calibration` - an iso temp program converts through calibration.
205. `test_iso_owned_run_zeroes_heater_on_scan_failure` - an owned iso run that fails before the AI scan starts drives the heater to 0 V.
206. `test_iso_owned_run_zeroes_heater_on_completion` - an owned iso run that reaches its programmed end drives the heater to 0 V.
207. `test_iso_mode_stops_early_on_external_request` - IsoMode stops early on an external request.
208. `test_iso_mode_stop_is_resettable_for_a_second_run` - a prior stop does not poison the next iso run.
209. `test_create_mode_factory` - create_mode returns the correct mode instance.
210. `test_create_mode_unknown_raises` - create_mode raises KeyError for an unknown mode.
211. `test_validate_accepts_non_second_durations` - arm accepts fractional-second durations.
212. `test_validate_rejects_inconsistent_durations` - arm rejects inconsistent channel durations.
213. `test_fast_mode_with_temperature_program_runs_calibration_path` - a FastHeat temp program converts through calibration.
214. `test_fast_mode_fractional_seconds` - FastHeat collects the exact sample count for fractional durations.
215. `test_clip_modulation_warns_when_clipped` - clipping modulation outside the safe range warns.
216. `test_clip_modulation_silent_when_within_range` - clipping within the safe range is silent.
217. `test_zero_ao_drives_all_channels_to_zero` - zero_ao drives all channels to 0 V.
218. `test_finite_scan_single_shot_full_buffer` - a single-shot finite scan returns the exact sample count.
219. `test_slow_mode_stop_cancels_and_zeroes` - a SlowMode stop aborts early and zeroes the heater.
220. `test_flip_poll_interval_clamps` - the half-flip poll period stays inside [1 ms, 50 ms].
221. `test_slow_mode_stop_latency_is_small` - a Stop is honoured within a fraction of a second despite the slower poll.
222. `test_fast_mode_stop_returns_early_and_zeroes` - a FastHeat stop returns early and zeroes the heater.
223. `test_mode_stop_without_run_is_noop` - a mode stop before any run is a no-op.
224. `test_slow_mode_injected_off_ring` - the SlowMode injected path uses caller-supplied snapshot data.
225. `test_slow_mode_injected_uses_actual_ring_rate` - the injected path trims/demodulates at the ring's actual rate.
226. `test_slow_mode_injected_warns_on_short_frame` - a ring shallower than the ramp warns instead of returning a misaligned frame.
227. `test_slow_mode_injected_short_frame_after_stop_is_not_a_warning` - a frame shortened by Stop logs INFO, not WARNING.
228. `test_slow_mode_injected_stop_interrupts` - the SlowMode injected-path stop interrupts the ramp wait.
229. `test_arm_rejects_temperature_above_max` - arm rejects a temperature above the mode limit.
230. `test_arm_accepts_heat_iso_cool_in_range` - arm accepts a multi-segment program within limits.
231. `test_arm_rejects_cool_faster_than_max` - arm rejects cooling faster than MaxCoolRate.
232. `test_arm_rejects_heat_slower_than_min` - arm rejects heating slower than MinHeatRate.
233. `test_segments_to_program_heat_iso_cool` - the segments builder produces a correct heat-iso-cool program.
234. `test_segments_to_program_rejects_bad_segments` - the segments builder rejects invalid segments.
235. `test_arm_rejects_nonfinite_program` - arm rejects programs containing NaN/Inf.
236. `test_scan_data_generator_logs_absent_channel` - the data generator logs an absent AO channel held at 0 V.
237. `test_finite_scan_zeroes_ao_on_collect_exception` - an exception in the collect loop drives all AO channels to 0 V.
238. `test_finite_scan_rejects_trigger_without_primitive` - HardwareTrigger without a software-trigger primitive fails fast before arming.
239. `test_finite_scan_aborts_on_half_buffer_overrun` - a driver lapping the collector by a full buffer aborts fail-loud and zeroes AO.
240. `test_arm_rejects_oversized_ao_buffer` - a program whose AO buffer would exceed the RAM cap is rejected at arm.
241. `test_iso_arm_allows_long_program` - iso is exempt from the AO-buffer cap (1 s buffer); multi-hour iso programs still arm.

## tests/test_modulation.py - 22 functions / 22 cases

242. `test_apply_modulation_no_op_when_disabled` - zero-amplitude modulation leaves the output unchanged.
243. `test_apply_modulation_adds_sin_and_offset` - modulation adds a sinusoid and offset to the base signal.
244. `test_lockin_recovers_amplitude_and_phase` - lock-in recovers amplitude and phase from a noisy signal.
245. `test_lockin_rejects_invalid_inputs` - lock-in rejects a zero sample rate and invalid bandwidth.
246. `test_reference_phase_recovers_reference_lag` - reference-phase extraction recovers the fundamental lag.
247. `test_reference_phase_zero_for_dc_reference` - a DC reference yields phase zero.
248. `test_lockin_with_measured_reference_subtracts_reference_phase` - a measured reference subtracts its phase from the report.
249. `test_lockin_reference_shape_must_match` - lock-in requires the signal and reference to be equal length.
250. `test_modulation_params_measured_reference_flag` - ModulationParams preserves use_measured_reference.
251. `test_fft_demodulate_recovers_fundamental_amp_and_phase` - FFT demod recovers exact amp/phase from a clean tone.
252. `test_fft_demodulate_extracts_harmonics` - FFT demod recovers multiple harmonics independently.
253. `test_fft_demodulate_phase_matches_lockin` - FFT and lock-in report matching phase on a stationary signal.
254. `test_fft_demodulate_leakage_flags_off_grid_tone` - the leakage fraction detects power at off-grid frequencies.
255. `test_fft_demodulate_handles_aliased_harmonic` - FFT demod returns NaN for harmonics above Nyquist.
256. `test_fft_demodulate_rejects_invalid_inputs` - FFT demod rejects a zero rate and invalid frequency.
257. `test_ao_period_integrity_seamless_when_integer_cycles` - an integer-cycle buffer is seamless, zero drift.
258. `test_ao_period_integrity_flags_production_iso_settings` - the production 37.5 Hz config is not seamless.
259. `test_ao_period_integrity_19200_sample_buffer_is_clean` - a 36-cycle buffer at 37.5 Hz is seamless.
260. `test_ao_period_integrity_flags_aliased_frequency` - an aliased (above-Nyquist) frequency is flagged.
261. `test_ao_period_integrity_rejects_bad_inputs` - check_ao_period_integrity rejects empty/invalid inputs.
262. `test_lockin_valid_mask_marks_settling_edges` - the valid mask marks the sosfiltfilt settling transient at the edges.
263. `test_lockin_valid_all_false_for_short_signal` - a too-short signal yields an all-false valid mask.

## tests/test_session_stats.py - 3 functions / 3 cases

264. `test_empty_summary` - an empty summary shows no recorded actions.
265. `test_record_counts_and_get` - record counts actions and get returns the values.
266. `test_summary_is_sorted_and_readable` - the summary sorts keys alphabetically.

## tests/test_ui_settings.py - 6 functions / 6 cases

267. `test_loads_packaged_defaults` - packaged defaults populate every documented UI field.
268. `test_falls_back_when_file_missing` - a missing file uses defaults without an exception.
269. `test_partial_override` - a partial JSON override keeps the remaining fields at defaults.
270. `test_full_override` - a full JSON override (Plot/Ring/Demod/Sliders) works.
271. `test_bad_channel_key_dropped` - invalid channel keys are dropped, valid ones kept.
272. `test_channel_indices_coerce_to_tuple_of_ints` - channel indices coerce from a list to an int tuple.
