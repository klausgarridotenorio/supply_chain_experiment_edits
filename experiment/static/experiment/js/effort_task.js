////////////////////////////////////////////////////////////////////////////////
// Slider effort task
//
// Adapted from the Qualtrics reference implementation: the grid building,
// live value labels, live score counting, the cosmetic per-row offsets and
// the pacing_timestamps logic are kept. Deliberately REMOVED:
//   * all Qualtrics API calls (embedded data -> replaced by hidden oTree
//     form inputs, see syncHiddenFields),
//   * every timer/limit (time limit, NPA, delay, profit reduction) -- the
//     task is untimed,
//   * all Next-button blocking -- the button stays clickable throughout.
////////////////////////////////////////////////////////////////////////////////

document.addEventListener('DOMContentLoaded', () => {
  const N = js_vars.num_sliders;
  const TARGET = js_vars.target;
  const MIN = js_vars.slider_min;
  const MAX = js_vars.slider_max;
  const COLS = js_vars.cols;
  // Horizontal per-row offsets (from the reference implementation) so the
  // sliders cannot be visually aligned across rows.
  const OFFSETS = [0, 14, 32, 6, 24, 10, 0, 28, 12, 34, 4, 20];
  // A slider only counts as "placed" for the pacing log if it stays on the
  // target for this long (same debounce as the reference implementation).
  const PLACEMENT_DEBOUNCE_MS = 500;

  const grid = document.getElementById('slider-grid');
  const scoreEl = document.getElementById('sliders-at-target');
  const totalEl = document.getElementById('sliders-total');

  // Hidden oTree form inputs (names match EffortTask.form_fields).
  const fieldScore =
      document.getElementById('id_effort_put_number_of_sliders');
  const fieldTime =
      document.getElementById('id_effort_put_time_on_sliders');
  const fieldPacing =
      document.getElementById('id_effort_put_relative_time_on_sliders');

  // ── Time measurement & pacing ───────────────────────────────────────────
  const startTime = Date.now();
  // k-th entry = ms since page load at which the (k+1)-th slider was
  // durably placed on the target.
  const pacingTimestamps = [];
  const sliderTimers = {};  // per-slider debounce timers
  const onTarget = new Array(N).fill(0);
  let score = 0;

  totalEl.textContent = String(N);

  // Keep the hidden inputs current at all times, so the values are correct
  // whenever the participant clicks Next -- even mid-drag or right away.
  function syncHiddenFields() {
    fieldScore.value = String(score);
    fieldTime.value = ((Date.now() - startTime) / 1000).toFixed(1);
    fieldPacing.value = JSON.stringify(pacingTimestamps);
  }

  // ── Build the grid ──────────────────────────────────────────────────────
  for (let i = 0; i < N; i++) {
    const row = document.createElement('div');
    row.className = 'slider-row';
    row.style.marginLeft =
        OFFSETS[Math.floor(i / COLS) % OFFSETS.length] + 'px';

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = String(MIN);
    slider.max = String(MAX);
    slider.step = '1';
    slider.value = String(MIN);

    const label = document.createElement('span');
    label.className = 'slider-value';
    label.textContent = slider.value;

    slider.addEventListener('input', () => {
      const v = parseInt(slider.value, 10);
      label.textContent = String(v);

      // ── Live score ──
      const newFlag = (v === TARGET) ? 1 : 0;
      if (newFlag !== onTarget[i]) {
        score += newFlag - onTarget[i];
        onTarget[i] = newFlag;
        scoreEl.textContent = String(score);
      }

      // ── Pacing logic (adapted 1:1 from the reference) ──
      if (v === TARGET) {
        if (!sliderTimers[i]) {
          sliderTimers[i] = setTimeout(() => {
            if (score > pacingTimestamps.length) {
              const placementTime =
                  Date.now() - startTime - PLACEMENT_DEBOUNCE_MS;
              while (pacingTimestamps.length < score) {
                pacingTimestamps.push(placementTime);
              }
            }
            sliderTimers[i] = null;
            syncHiddenFields();
          }, PLACEMENT_DEBOUNCE_MS);
        }
      } else if (sliderTimers[i]) {
        clearTimeout(sliderTimers[i]);
        sliderTimers[i] = null;
      }

      syncHiddenFields();
    });

    row.appendChild(slider);
    row.appendChild(label);
    grid.appendChild(row);
  }

  syncHiddenFields();

  // Finalize the values the moment the form is actually submitted
  // (equivalent to the reference's addOnPageSubmit, minus Qualtrics).
  document.getElementById('form').addEventListener('submit',
      syncHiddenFields);
});
