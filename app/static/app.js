const $ = (id) => document.getElementById(id);
let map, layer, plan;

function setStatus(text, isError = false) {
  const el = $("status");
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.toggle("error", isError);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function initMap() {
  if (map) return;
  map = L.map("map");
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  layer = L.layerGroup().addTo(map);
}

function showDay(index) {
  const day = plan.days[index];
  document.querySelectorAll("#tabs button").forEach((b, i) => b.classList.toggle("active", i === index));

  const list = $("stops");
  list.innerHTML = "";
  layer.clearLayers();
  const points = [];
  const markers = [];

  day.stops.forEach((stop, i) => {
    const li = document.createElement("li");
    li.className = "stop";
    li.innerHTML = `
      <div class="num">${i + 1}</div>
      <div>
        <h4>${escapeHtml(stop.name)}</h4>
        <div class="meta">${escapeHtml(stop.time)} · ~${stop.duration_min} хв
          ${stop.verified ? "" : '<span class="badge">· координати не підтверджено</span>'}</div>
        <p>${escapeHtml(stop.description)}</p>
      </div>`;
    list.appendChild(li);

    if (!stop.verified) return;
    const icon = L.divIcon({ className: "", html: `<div class="pin">${i + 1}</div>`, iconSize: [26, 26] });
    const marker = L.marker([stop.lat, stop.lon], { icon })
      .bindPopup(`<b>${escapeHtml(stop.name)}</b><br>${escapeHtml(stop.time)}`)
      .addTo(layer);
    points.push([stop.lat, stop.lon]);
    markers.push(marker);
    li.addEventListener("click", () => { map.setView([stop.lat, stop.lon], 16); marker.openPopup(); });
  });

  if (points.length > 1) L.polyline(points, { color: "#2f6f8f", weight: 3, dashArray: "6 6" }).addTo(layer);
  if (points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 15 });
  else map.setView([plan.city.lat, plan.city.lon], 12);
}

function render(data) {
  plan = data;
  $("result").hidden = false;
  const n = data.days.length;
  $("city-name").textContent = `${data.city.name}: ${n} ${n === 1 ? "день" : n < 5 ? "дні" : "днів"}`;
  $("summary").textContent = data.summary;
  $("tips").innerHTML = data.tips.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  $("model").textContent = `Маршрут згенеровано моделлю ${data.model}. Місто: ${data.city.display_name}.`;

  const tabs = $("tabs");
  tabs.innerHTML = "";
  data.days.forEach((day, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = `День ${day.day}: ${day.title}`;
    b.addEventListener("click", () => showDay(i));
    tabs.appendChild(b);
  });

  initMap();
  setTimeout(() => { map.invalidateSize(); showDay(0); }, 0);
  $("result").scrollIntoView({ behavior: "smooth" });
}

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = {
    city: $("city").value,
    days: Number($("days").value),
    pace: $("pace").value,
    budget: $("budget").value,
    interests: [...document.querySelectorAll("#interests input:checked")].map((i) => i.value),
  };
  $("submit").disabled = true;
  setStatus("Шукаю місто й складаю маршрут… зазвичай 5–15 секунд");
  try {
    const response = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? "Перевірте введені дані." : data.detail;
      throw new Error(detail || `Помилка ${response.status}`);
    }
    setStatus("");
    render(data);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    $("submit").disabled = false;
  }
});
