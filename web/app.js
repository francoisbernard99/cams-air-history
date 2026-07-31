/* Interactive map.
 *
 * The only script on the page, and everything below it degrades: the archive
 * charts are rendered by Python and readable without any of this. What the
 * script adds is the live part -- click a point, or draw a zone, and the
 * browser asks Open-Meteo directly for that spot.
 *
 * No map library and no tile server: the outline is SVG rendered at build time,
 * and the projection is inverted here in three lines of arithmetic.
 */
/* Theme switch. Kept in its own block, before the map guard below: the button
   has to keep working on a page where the map never initialised. */
(function () {
  "use strict";

  var button = document.getElementById("theme-toggle");
  if (!button) return;

  function apply(dark) {
    if (dark) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    button.setAttribute("aria-pressed", String(dark));
    button.textContent = dark ? "Thème clair" : "Thème sombre";
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
  }

  apply(document.documentElement.getAttribute("data-theme") === "dark");

  button.addEventListener("click", function () {
    apply(document.documentElement.getAttribute("data-theme") !== "dark");
  });
})();

(function () {
  "use strict";

  var config = JSON.parse(document.getElementById("map-config").textContent);
  var svg = document.getElementById("map");
  var panel = document.getElementById("map-panel");
  var status = document.getElementById("map-status");
  var modeButtons = document.querySelectorAll("[data-mode]");
  if (!svg || !panel) return;

  var API = "https://air-quality-api.open-meteo.com/v1/air-quality";
  var HISTORY_DAYS = 30;
  var ZONE_SAMPLES = 12;      // one request covers them all
  var mode = "point";
  var pending = null;

  /* ---- projection ------------------------------------------------------ */

  function toLonLat(x, y) {
    var mx = x / config.scale + config.xMin;
    var my = config.yMax - y / config.scale;
    return {
      lon: mx * 180 / Math.PI,
      lat: (2 * Math.atan(Math.exp(my)) - Math.PI / 2) * 180 / Math.PI
    };
  }

  function svgPoint(event) {
    var point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(svg.getScreenCTM().inverse());
  }

  /* ---- land test ------------------------------------------------------- */
  /* Parsed from the outlines already on the page, so it costs no extra bytes.
     Without it, a zone average would quietly fold in cells over open sea. */

  var landRings = [];
  Array.prototype.forEach.call(svg.querySelectorAll(".region"), function (node) {
    node.getAttribute("d").split("Z").forEach(function (part) {
      var ring = [];
      part.replace(/[ML](-?[\d.]+),(-?[\d.]+)/g, function (_, x, y) {
        ring.push([parseFloat(x), parseFloat(y)]);
        return "";
      });
      if (ring.length > 2) landRings.push(ring);
    });
  });

  function onLand(x, y) {
    for (var r = 0; r < landRings.length; r++) {
      var ring = landRings[r], inside = false;
      for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
        if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
          inside = !inside;
        }
      }
      if (inside) return true;
    }
    return false;
  }

  /* ---- data ------------------------------------------------------------ */

  function request(points) {
    var url = API +
      "?latitude=" + points.map(function (p) { return p.lat.toFixed(4); }).join(",") +
      "&longitude=" + points.map(function (p) { return p.lon.toFixed(4); }).join(",") +
      "&hourly=" + config.species.join(",") +
      "&past_days=" + HISTORY_DAYS + "&forecast_days=1";

    return fetch(url).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    }).then(function (payload) {
      return Array.isArray(payload) ? payload : [payload];
    });
  }

  function quantile(sorted, q) {
    if (!sorted.length) return null;
    var position = (sorted.length - 1) * q;
    var low = Math.floor(position), high = Math.ceil(position);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  }

  /* One entry per day: the median of every hourly value collected that day,
     across every sampled point, with the 10th-90th percentile band around it.
     The median rather than the mean, because a single modelled spike should not
     drag a whole day with it. */
  function daily(payloads, species) {
    var buckets = {};
    payloads.forEach(function (payload) {
      var hours = payload.hourly.time;
      var values = payload.hourly[species] || [];
      for (var i = 0; i < hours.length; i++) {
        if (values[i] === null || values[i] === undefined) continue;
        var day = hours[i].slice(0, 10);
        (buckets[day] = buckets[day] || []).push(values[i]);
      }
    });
    return Object.keys(buckets).sort().map(function (day) {
      var sorted = buckets[day].sort(function (a, b) { return a - b; });
      return {
        day: day,
        median: quantile(sorted, 0.5),
        low: quantile(sorted, 0.1),
        high: quantile(sorted, 0.9)
      };
    });
  }

  /* ---- drawing --------------------------------------------------------- */

  function niceTicks(low, high) {
    low = Math.min(0, low);
    var span = (high - low) || 1, raw = span / 3;
    var step = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    [1, 2, 5, 10].some(function (m) {
      if (step * m >= raw) { step = step * m; return true; }
      return false;
    });
    var ticks = [];
    for (var v = low; v <= high + step / 2; v += step) ticks.push(v);
    return ticks;
  }

  function format(value) {
    if (value === null) return "—";
    if (value >= 100) return value.toFixed(0);
    if (value >= 10) return value.toFixed(0);
    return value.toFixed(1);
  }

  function chart(series, unit) {
    if (!series.length) return '<p class="empty">Aucune valeur.</p>';

    var w = 280, h = 150, left = 40, right = 12, top = 12, bottom = 26;
    var pw = w - left - right, ph = h - top - bottom;
    var all = series.reduce(function (acc, d) {
      return acc.concat([d.median, d.low, d.high]);
    }, []);
    var ticks = niceTicks(Math.min.apply(null, all), Math.max.apply(null, all));
    var yMin = ticks[0], yMax = ticks[ticks.length - 1], span = (yMax - yMin) || 1;

    function X(i) {
      return series.length === 1 ? left + pw / 2 : left + pw * i / (series.length - 1);
    }
    function Y(v) { return top + ph * (1 - (v - yMin) / span); }

    var out = '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" role="img">';
    ticks.forEach(function (t) {
      out += '<line class="grid" x1="' + left + '" y1="' + Y(t).toFixed(1) +
             '" x2="' + (w - right) + '" y2="' + Y(t).toFixed(1) + '"/>' +
             '<text class="tick" x="' + (left - 6) + '" y="' + (Y(t) + 3.5).toFixed(1) +
             '" text-anchor="end">' + format(t) + "</text>";
    });

    var upper = series.map(function (d, i) { return X(i).toFixed(1) + "," + Y(d.high).toFixed(1); });
    var lower = series.map(function (d, i) { return X(i).toFixed(1) + "," + Y(d.low).toFixed(1); }).reverse();
    out += '<polygon class="band" points="' + upper.concat(lower).join(" ") + '"/>';

    out += '<path class="line" d="' + series.map(function (d, i) {
      return (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(d.median).toFixed(1);
    }).join(" ") + '"/>';

    [0, series.length - 1].forEach(function (i, n) {
      var label = series[i].day.slice(8) + "/" + series[i].day.slice(5, 7);
      out += '<text class="tick" x="' + X(i).toFixed(1) + '" y="' + (h - 8) +
             '" text-anchor="' + (n ? "end" : "start") + '">' + label + "</text>";
    });

    var last = series[series.length - 1];
    out += '<circle class="marker-ring" cx="' + X(series.length - 1).toFixed(1) +
           '" cy="' + Y(last.median).toFixed(1) + '" r="6"/>' +
           '<circle class="marker" cx="' + X(series.length - 1).toFixed(1) +
           '" cy="' + Y(last.median).toFixed(1) + '" r="4"/>';

    series.forEach(function (d, i) {
      out += '<circle class="hit" cx="' + X(i).toFixed(1) + '" cy="' + Y(d.median).toFixed(1) +
             '" r="7"><title>' + d.day + " — " + format(d.median) + " " + unit +
             " (" + format(d.low) + "–" + format(d.high) + ")</title></circle>";
    });

    return out + "</svg>";
  }

  /* The table twin. Every other chart on this page has one, and a value that
     can only be reached by hovering is a value some readers cannot reach. */
  function table(series, unit) {
    var rows = series.slice(-14).map(function (d) {
      return "<tr><td>" + d.day + "</td><td>" + format(d.median) +
             "</td><td>" + format(d.low) + "</td><td>" + format(d.high) + "</td></tr>";
    }).join("");
    return '<details><summary>Voir les valeurs</summary><div class="table-wrap">' +
           "<table><caption>Les quatorze derniers jours, en " + unit +
           ".</caption><thead><tr><th>Jour</th><th>Médiane</th><th>10ᵉ c.</th>" +
           "<th>90ᵉ c.</th></tr></thead><tbody>" + rows +
           "</tbody></table></div></details>";
  }

  function render(title, subtitle, payloads) {
    var units = payloads[0].hourly_units || {};
    var html = "<h3>" + title + "</h3><p class=\"note\">" + subtitle + "</p>" +
               '<div class="panels">';

    config.species.forEach(function (species) {
      var series = daily(payloads, species);
      var unit = units[species] || "";
      var latest = series.length ? series[series.length - 1].median : null;
      html += '<div class="panel"><h3>' + config.labels[species] +
              '<span class="note"> — ' + unit + "</span></h3>" +
              '<p class="panel-value">' + format(latest) + "</p>" +
              chart(series, unit) + table(series, unit) + "</div>";
    });

    panel.innerHTML = html + "</div>" +
      '<p class="note">Médiane horaire de chaque journée ; la zone claire couvre ' +
      "les 10ᵉ à 90ᵉ centiles. Valeurs modélisées CAMS sur une maille d'environ " +
      "11 km, pas des mesures.</p>";
  }

  /* ---- interaction ----------------------------------------------------- */

  function say(message, busy) {
    status.textContent = message;
    status.className = busy ? "note busy" : "note";
  }

  function load(points, title, subtitle) {
    var token = {};
    pending = token;
    say("Interrogation d'Open-Meteo…", true);

    request(points).then(function (payloads) {
      if (pending !== token) return;   // a newer click won
      render(title, subtitle, payloads);
      say(points.length === 1 ? "Point interrogé." : points.length + " points moyennés.");
    }).catch(function (error) {
      if (pending !== token) return;
      say("La source n'a pas répondu (" + error.message + "). Réessayer plus tard.");
    });
  }

  function marker(x, y) {
    var existing = svg.querySelector(".pin");
    if (existing) existing.remove();
    var pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pin.setAttribute("class", "pin");
    pin.setAttribute("cx", x);
    pin.setAttribute("cy", y);
    pin.setAttribute("r", 6);
    svg.appendChild(pin);
  }

  function pickPoint(x, y) {
    var here = toLonLat(x, y);
    marker(x, y);
    load([here],
         here.lat.toFixed(3) + "°N, " + here.lon.toFixed(3) + "°E",
         "Trente derniers jours au point cliqué.");
  }

  /* Zone: a grid of sample points inside the drawn rectangle, keeping only
     those over land, sent as a single request. */
  function pickZone(x1, y1, x2, y2) {
    var points = [], columns = 4, rows = 3;
    for (var c = 0; c < columns; c++) {
      for (var r = 0; r < rows; r++) {
        var x = x1 + (x2 - x1) * (c + 0.5) / columns;
        var y = y1 + (y2 - y1) * (r + 0.5) / rows;
        if (onLand(x, y)) points.push(toLonLat(x, y));
        if (points.length >= ZONE_SAMPLES) break;
      }
    }
    if (!points.length) {
      say("Aucun point terrestre dans cette zone.");
      return;
    }
    load(points, points.length + " points échantillonnés",
         "Médiane sur l'ensemble des points de la zone, trente derniers jours.");
  }

  /* ---- commune search -------------------------------------------------- */
  /* The index is 35 000 communes: too heavy to inline, so it is fetched from
     this same site on the first keystroke and kept for the session. Nothing is
     asked of a third party. */

  var search = document.getElementById("commune");
  var results = document.getElementById("commune-results");
  var index = null;
  var loading = null;
  var highlighted = -1;

  function fold(text) {
    // Accents and punctuation must not stand between someone and their town:
    // "st etienne" has to find "Saint-Étienne" is beyond this, but "st-etienne"
    // and "Saint-Etienne" should at least agree on their letters.
    return text.toLowerCase().normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/['’\-\s]/g, "");
  }

  function loadIndex() {
    if (index) return Promise.resolve(index);
    if (loading) return loading;

    // Opened straight from disk, a browser refuses fetch() even for a file
    // sitting in the same folder. Saying so beats reporting "NetworkError",
    // which sends the reader looking for a problem that is not theirs.
    if (location.protocol === "file:") {
      say("La recherche demande que la page soit servie par un serveur. " +
          "Depuis le dossier public : python3 -m http.server 8000");
      return Promise.reject(new Error("file://"));
    }

    say("Chargement de la liste des communes…", true);
    loading = fetch(config.communes).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    }).then(function (data) {
      var noms = data.noms.split("\n");
      index = {
        noms: noms,
        plies: noms.map(fold),
        cp: data.cp.split("\n"),
        lon: data.lon,
        lat: data.lat
      };
      say("Tapez le début d'un nom de commune.");
      return index;
    }).catch(function (error) {
      loading = null;
      say("Liste des communes indisponible (" + error.message + "). " +
          "Le reste de la carte fonctionne : cliquez directement dessus.");
      throw error;
    });
    return loading;
  }

  /* The index is sorted by population, so scanning in order and stopping at
     eight already puts the largest matches first -- no scoring needed. */
  function lookup(query, limit) {
    var plie = fold(query);
    var chiffres = /^\d{2,5}$/.test(query.trim());
    var found = [];
    for (var i = 0; i < index.noms.length && found.length < limit; i++) {
      var hit = chiffres
        ? index.cp[i].indexOf(query.trim()) === 0
        : index.plies[i].indexOf(plie) === 0;
      if (hit) found.push(i);
    }
    return found;
  }

  function closeResults() {
    results.hidden = true;
    results.innerHTML = "";
    search.setAttribute("aria-expanded", "false");
    highlighted = -1;
  }

  function showResults(found) {
    if (!found.length) {
      results.innerHTML = '<li class="empty" role="presentation">Aucune commune.</li>';
    } else {
      results.innerHTML = found.map(function (i, rank) {
        return '<li role="option" id="commune-' + rank + '" data-index="' + i +
               '" aria-selected="false"><strong>' + index.noms[i] +
               "</strong> <span class=\"note\">" + index.cp[i] + "</span></li>";
      }).join("");
    }
    results.hidden = false;
    search.setAttribute("aria-expanded", "true");
    highlighted = -1;
  }

  function choose(i) {
    var lon = index.lon[i], lat = index.lat[i];
    var x = (Math.PI * lon / 180 - config.xMin) * config.scale;
    var mercY = Math.log(Math.tan(Math.PI / 4 + Math.PI * lat / 360));
    var y = (config.yMax - mercY) * config.scale;

    marker(x, y);
    closeResults();
    search.value = index.noms[i];
    load([{ lat: lat, lon: lon }],
         index.noms[i] + " — " + index.cp[i],
         "Trente derniers jours sur la maille du modèle qui couvre cette commune.");
  }

  function refresh() {
    var query = search.value.trim();
    if (query.length < 2) { closeResults(); return; }
    loadIndex().then(function () { showResults(lookup(query, 8)); })
               .catch(function () { closeResults(); });
  }

  var typing = null;
  search.addEventListener("input", function () {
    clearTimeout(typing);
    typing = setTimeout(refresh, 120);
  });

  search.addEventListener("keydown", function (event) {
    var options = results.querySelectorAll("li[data-index]");
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!options.length) return;
      event.preventDefault();
      highlighted += event.key === "ArrowDown" ? 1 : -1;
      if (highlighted < 0) highlighted = options.length - 1;
      if (highlighted >= options.length) highlighted = 0;
      Array.prototype.forEach.call(options, function (node, rank) {
        node.setAttribute("aria-selected", String(rank === highlighted));
      });
      search.setAttribute("aria-activedescendant", "commune-" + highlighted);
    } else if (event.key === "Enter") {
      event.preventDefault();
      var pick = options[highlighted >= 0 ? highlighted : 0];
      if (pick) choose(parseInt(pick.getAttribute("data-index"), 10));
    } else if (event.key === "Escape") {
      closeResults();
    }
  });

  results.addEventListener("click", function (event) {
    var item = event.target.closest("li[data-index]");
    if (item) choose(parseInt(item.getAttribute("data-index"), 10));
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest(".map-search")) closeResults();
  });

  /* ---- station layer --------------------------------------------------- */
  /* The markers are already in the SVG, drawn by Python. All this does is
     decide which ones are visible, so the layer works the moment the page
     renders rather than after a round trip. */

  var stationsGroup = document.getElementById("stations");
  var stationsFilter = document.getElementById("stations-filter");
  var stationsNote = document.getElementById("stations-note");

  if (stationsFilter && stationsGroup) {
    stationsFilter.addEventListener("change", function () {
      var showing = stationsFilter.value;
      stationsGroup.setAttribute("data-showing", showing);
      stationsNote.hidden = showing === "none";
      if (showing !== "none") {
        var shown = stationsGroup.querySelectorAll(
          showing === "all" ? ".station" : '.station[data-type="' + showing + '"]'
        ).length;
        say(shown + " stations affichées. Survolez-en une pour son type.");
      }
    });
  }

  /* ---- zone drawing ---------------------------------------------------- */

  var drag = null;
  var box = svg.querySelector(".zone-box");

  svg.addEventListener("pointerdown", function (event) {
    if (mode !== "zone") return;
    var p = svgPoint(event);
    drag = { x: p.x, y: p.y };
    svg.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  svg.addEventListener("pointermove", function (event) {
    if (!drag) return;
    var p = svgPoint(event);
    box.setAttribute("x", Math.min(drag.x, p.x));
    box.setAttribute("y", Math.min(drag.y, p.y));
    box.setAttribute("width", Math.abs(p.x - drag.x));
    box.setAttribute("height", Math.abs(p.y - drag.y));
    box.style.display = "block";
  });

  svg.addEventListener("pointerup", function (event) {
    if (!drag) return;
    var p = svgPoint(event);
    var x1 = Math.min(drag.x, p.x), x2 = Math.max(drag.x, p.x);
    var y1 = Math.min(drag.y, p.y), y2 = Math.max(drag.y, p.y);
    drag = null;
    if (x2 - x1 > 8 && y2 - y1 > 8) pickZone(x1, y1, x2, y2);
    else say("Zone trop petite. Tracez un rectangle plus large.");
  });

  svg.addEventListener("click", function (event) {
    if (mode !== "point") return;
    var p = svgPoint(event);
    pickPoint(p.x, p.y);
  });

  Array.prototype.forEach.call(modeButtons, function (button) {
    button.addEventListener("click", function () {
      mode = button.getAttribute("data-mode");
      Array.prototype.forEach.call(modeButtons, function (other) {
        other.setAttribute("aria-pressed", String(other === button));
      });
      box.style.display = "none";
      say(mode === "point"
        ? "Cliquez n'importe où sur la carte."
        : "Tracez un rectangle sur la carte.");
    });
  });

  /* The five archived points are keyboard-reachable, so the map is usable
     without a mouse even though free clicking is not. */
  Array.prototype.forEach.call(svg.querySelectorAll(".site"), function (node) {
    function choose() {
      pickPoint(parseFloat(node.getAttribute("cx")), parseFloat(node.getAttribute("cy")));
    }
    node.addEventListener("click", function (event) { event.stopPropagation(); choose(); });
    node.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
    });
  });

  document.getElementById("map-figure").hidden = false;
  say("Cliquez n'importe où sur la carte.");
})();
