const $ = (id) => document.getElementById(id);

const state = {
  manifest: null,
  model: "",
  region: "us",
  field: "",
  init: "",
  hour: 0,
  view: "both",
  playing: false,
  timer: 0,
};

const lenses = {
  wide: { scale: 1, x: 0, y: 0 },
  reel: { scale: 1, x: 0, y: 0 },
};

function runs() {
  return state.manifest.models[state.model].runs;
}

function currentRun() {
  return runs().find((run) => run.init === state.init) || runs()[0];
}

function hours() {
  const run = currentRun();
  return (run.fields[state.field] || { hours: [0] }).hours;
}

function formatInit(key) {
  const months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
  const month = months[Number(key.slice(4, 6)) - 1] || key.slice(4, 6);
  return `${key.slice(6, 8)} ${month} ${key.slice(8, 10)}Z`;
}

function fillSelect(select, pairs, value) {
  select.replaceChildren();
  for (const [id, label] of pairs) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = label;
    select.appendChild(option);
  }
  if (pairs.some(([id]) => id === value)) select.value = value;
}

function readHash() {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  return {
    model: params.get("m") || "",
    region: params.get("r") || "",
    field: params.get("f") || "",
    init: params.get("i") || "",
    hour: params.get("h"),
    view: params.get("v") || "",
  };
}

function writeHash() {
  const params = new URLSearchParams({
    m: state.model,
    r: state.region,
    f: state.field,
    i: state.init,
    h: String(state.hour),
    v: state.view,
  });
  history.replaceState(null, "", `#${params}`);
}

function chooseDefaults(pref) {
  const models = Object.keys(state.manifest.models);
  state.model = models.includes(pref.model) ? pref.model : models[0];
  const regions = Object.keys(state.manifest.regions);
  state.region = regions.includes(pref.region) ? pref.region : regions[0];
  const available = runs();
  state.init = available.some((run) => run.init === pref.init) ? pref.init : available[0].init;
  const fields = Object.keys(currentRun().fields);
  state.field = fields.includes(pref.field) ? pref.field : fields[0];
  const list = hours();
  const wanted = pref.hour == null ? list[0] : Number(pref.hour);
  state.hour = list.includes(wanted) ? wanted : list[0];
  state.view = ["both", "wide", "reel"].includes(pref.view) ? pref.view : "both";
}

function paintControls() {
  const models = Object.entries(state.manifest.models).map(([id, body]) => [id, body.label]);
  const regions = Object.entries(state.manifest.regions).map(([id, body]) => [id, body.label]);
  const fields = Object.entries(currentRun().fields).map(([id, body]) => [id, body.label]);
  const inits = runs().map((run) => [run.init, formatInit(run.init)]);
  fillSelect($("model"), models, state.model);
  fillSelect($("region"), regions, state.region);
  fillSelect($("field"), fields, state.field);
  fillSelect($("init"), inits, state.init);
  $("view").value = state.view;
  document.body.dataset.view = state.view;

  const list = hours();
  const slider = $("slider");
  slider.max = String(Math.max(0, list.length - 1));
  slider.value = String(Math.max(0, list.indexOf(state.hour)));
  const field = currentRun().fields[state.field];
  $("hour-label").textContent = `f${String(state.hour).padStart(3, "0")}`;
  const body = state.manifest.models[state.model];
  $("stamp").textContent = `${body.label}  ·  ${formatInit(state.init)}  ·  ${field.unit || "chart"}`;
  $("live-credit").textContent = body.attribution === "ecmwf"
    ? "Source: ECMWF open data, CC BY 4.0. This product is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF). Modified for display."
    : "NOAA model data, public domain. Basemap: U.S. Census Bureau TIGER/Line and Natural Earth, public domain.";
}

function frameUrl(aspect) {
  return `frames/${state.model}/${state.init}/${state.field}/${state.region}/${aspect}/f${String(state.hour).padStart(3, "0")}.webp`;
}

function applyLens(port, img, lens) {
  const width = port.clientWidth;
  const height = port.clientHeight;
  const minX = width * (1 - lens.scale);
  const minY = height * (1 - lens.scale);
  lens.x = Math.min(0, Math.max(minX, lens.x));
  lens.y = Math.min(0, Math.max(minY, lens.y));
  img.style.transform = `translate(${lens.x}px, ${lens.y}px) scale(${lens.scale})`;
}

const frameToken = { wide: 0, reel: 0 };

function showFrame(aspect) {
  const port = $(`${aspect}-port`);
  const img = $(`${aspect}-img`);
  const note = port.querySelector(".empty");
  const alt = `${state.manifest.models[state.model].label}, ${currentRun().fields[state.field].label}, ${state.manifest.regions[state.region].label}, ${aspect}, hour ${state.hour}`;
  const token = ++frameToken[aspect];
  img.alt = alt;
  img.classList.add("is-hidden");
  note.hidden = true;
  img.onload = () => {
    if (token !== frameToken[aspect]) return;
    img.classList.remove("is-hidden");
    note.hidden = true;
    applyLens(port, img, lenses[aspect]);
  };
  img.onerror = () => {
    if (token !== frameToken[aspect]) return;
    img.classList.add("is-hidden");
    note.hidden = false;
  };
  img.removeAttribute("src");
  img.src = frameUrl(aspect);
}

function render() {
  paintControls();
  writeHash();
  showFrame("wide");
  showFrame("reel");
}

function setHourIndex(index) {
  const list = hours();
  const next = list[Math.max(0, Math.min(list.length - 1, index))];
  if (next == null || next === state.hour) return;
  state.hour = next;
  render();
}

function zoomAt(aspect, clientX, clientY, factor) {
  const port = $(`${aspect}-port`);
  const img = $(`${aspect}-img`);
  const lens = lenses[aspect];
  const rect = port.getBoundingClientRect();
  const cx = clientX - rect.left;
  const cy = clientY - rect.top;
  const next = Math.min(8, Math.max(1, lens.scale * factor));
  const k = next / lens.scale;
  lens.x = cx - (cx - lens.x) * k;
  lens.y = cy - (cy - lens.y) * k;
  lens.scale = next;
  applyLens(port, img, lens);
}

function bindLens(aspect) {
  const port = $(`${aspect}-port`);
  const pointers = new Map();
  let pinch = 0;

  port.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    zoomAt(aspect, event.clientX, event.clientY, factor);
  }, { passive: false });

  port.addEventListener("pointerdown", (event) => {
    port.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = Math.hypot(a.x - b.x, a.y - b.y);
    }
  });
  port.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    const prev = pointers.get(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch > 0) zoomAt(aspect, (a.x + b.x) / 2, (a.y + b.y) / 2, dist / pinch);
      pinch = dist;
      return;
    }
    const lens = lenses[aspect];
    lens.x += event.clientX - prev.x;
    lens.y += event.clientY - prev.y;
    applyLens(port, $(`${aspect}-img`), lens);
  });
  const end = (event) => {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinch = 0;
  };
  port.addEventListener("pointerup", end);
  port.addEventListener("pointercancel", end);
  port.addEventListener("dblclick", () => {
    lenses[aspect].scale = 1;
    lenses[aspect].x = 0;
    lenses[aspect].y = 0;
    applyLens(port, $(`${aspect}-img`), lenses[aspect]);
  });
}

function stopPlay() {
  state.playing = false;
  $("play").textContent = "Play";
  if (state.timer) window.clearInterval(state.timer);
  state.timer = 0;
}

function togglePlay() {
  if (state.playing) {
    stopPlay();
    return;
  }
  state.playing = true;
  $("play").textContent = "Pause";
  state.timer = window.setInterval(() => {
    const list = hours();
    const index = list.indexOf(state.hour);
    if (index >= list.length - 1) {
      stopPlay();
      return;
    }
    setHourIndex(index + 1);
  }, 700);
}

function onModel() {
  state.model = $("model").value;
  state.init = runs()[0].init;
  const fields = Object.keys(currentRun().fields);
  if (!fields.includes(state.field)) state.field = fields[0];
  const list = hours();
  if (!list.includes(state.hour)) state.hour = list[0];
  render();
}

function onField() {
  state.field = $("field").value;
  const list = hours();
  if (!list.includes(state.hour)) state.hour = list[Math.min(list.length - 1, Math.max(0, list.indexOf(state.hour)))];
  if (!list.includes(state.hour)) state.hour = list[0];
  render();
}

async function boot() {
  const response = await fetch("manifest.json", { cache: "no-store" });
  state.manifest = await response.json();
  const names = Object.keys(state.manifest.models || {});
  if (!names.length) {
    $("stamp").textContent = "No runs published yet";
    $("live-credit").textContent = "The next scheduled build will place charts here after a model run finishes.";
    return;
  }
  chooseDefaults(readHash());
  bindLens("wide");
  bindLens("reel");
  $("model").addEventListener("change", onModel);
  $("region").addEventListener("change", () => { state.region = $("region").value; render(); });
  $("field").addEventListener("change", onField);
  $("init").addEventListener("change", () => {
    state.init = $("init").value;
    const fields = Object.keys(currentRun().fields);
    if (!fields.includes(state.field)) state.field = fields[0];
    const list = hours();
    if (!list.includes(state.hour)) state.hour = list[0];
    render();
  });
  $("view").addEventListener("change", () => { state.view = $("view").value; render(); });
  $("slider").addEventListener("input", () => setHourIndex(Number($("slider").value)));
  $("prev").addEventListener("click", () => setHourIndex(hours().indexOf(state.hour) - 1));
  $("next").addEventListener("click", () => setHourIndex(hours().indexOf(state.hour) + 1));
  $("play").addEventListener("click", togglePlay);
  window.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") setHourIndex(hours().indexOf(state.hour) + 1);
    if (event.key === "ArrowLeft") setHourIndex(hours().indexOf(state.hour) - 1);
    if (event.key === " ") {
      event.preventDefault();
      togglePlay();
    }
  });
  window.addEventListener("resize", () => {
    applyLens($("wide-port"), $("wide-img"), lenses.wide);
    applyLens($("reel-port"), $("reel-img"), lenses.reel);
  });
  render();
}

boot().catch((error) => {
  $("stamp").textContent = "Could not read the catalog";
  console.error(error);
});
