(function(){
  "use strict";
  var DATA = window.LSN_DATA;
  var COLS = DATA.columns; // ["state","lat","lon","riskScore","riskLabel","landslideEvent","elevation","slope","histDensity","histDistance"]
  var C = { state:0, lat:1, lon:2, score:3, label:4, event:5, elevation:6, slope:7, density:8, distance:9 };
  var POINTS = DATA.points;
  var STATS = DATA.stats;

  function bandKey(label){
    if(label === "LOW") return "low";
    if(label === "MODERATE") return "moderate";
    if(label === "HIGH") return "high";
    return "veryhigh";
  }
  function bandTitle(label){
    if(label === "VERY HIGH") return "Very High";
    return label.charAt(0) + label.slice(1).toLowerCase();
  }
  function fmt1(n){ return (Math.round(n * 10) / 10).toFixed(1); }
  function fmtInt(n){ return n.toLocaleString("en-IN"); }

  /* ---------------- nav routing ---------------- */
  var navItems = document.querySelectorAll(".nav-item");
  var pages = document.querySelectorAll(".page");
  var pageTitle = document.getElementById("pageTitle");
  var pageSub = document.getElementById("pageSub");
  var titleMap = {
    dashboard: ["Dashboard", "V1 landslide susceptibility model — cleaned GSI sample points"],
    riskmap: ["Risk Map", "Model scores on existing GSI sample points"],
    alerts: ["Alerts", "Elevated-risk points from the V1 model"],
    fieldreports: ["Field Reports", "Field verification interface"],
    analytics: ["Analytics", "Real V1 dataset statistics"],
    about: ["About", "Model, training data, evaluation, and data sources"]
  };
  navItems.forEach(function(item){
    item.addEventListener("click", function(){ goToPage(item.getAttribute("data-page")); });
  });
  function goToPage(name){
    navItems.forEach(function(i){ i.classList.toggle("active", i.getAttribute("data-page") === name); });
    pages.forEach(function(p){ p.classList.toggle("active", p.id === "page-" + name); });
    var t = titleMap[name] || titleMap.dashboard;
    pageTitle.textContent = t[0];
    pageSub.textContent = t[1];
    if(name === "riskmap"){
      ensureRiskMapInit();
      setTimeout(function(){ if(riskMapInstance) riskMapInstance.invalidateSize(); }, 60);
    }
  }
  window.LSN_goToPage = goToPage;

  document.getElementById("collapseBtn").addEventListener("click", function(){
    var sb = document.getElementById("sidebar");
    sb.classList.toggle("collapsed");
    this.textContent = sb.classList.contains("collapsed") ? "›" : "‹";
  });

  /* ---------------- theme toggle (light default, dark optional, persisted) ---------------- */
  (function initTheme(){
    var root = document.documentElement;
    var btn = document.getElementById("themeToggleBtn");
    var icon = document.getElementById("themeToggleIcon");
    var label = document.getElementById("themeToggleLabel");
    if(!btn) return;

    function applyTheme(theme){
      if(theme === "dark"){
        root.setAttribute("data-theme", "dark");
        if(icon) icon.textContent = "☀";
        if(label) label.textContent = "Light";
      } else {
        root.removeAttribute("data-theme");
        if(icon) icon.textContent = "🌙";
        if(label) label.textContent = "Dark";
      }
      // Leaflet tiles/panes can mis-measure across a theme-driven layout tick; nudge them.
      if(riskMapInstance){ setTimeout(function(){ riskMapInstance.invalidateSize(); }, 80); }
    }

    var stored = null;
    try{ stored = localStorage.getItem("lsn-theme"); }catch(e){}
    applyTheme(stored === "dark" ? "dark" : "light");

    btn.addEventListener("click", function(){
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try{ localStorage.setItem("lsn-theme", next); }catch(e){}
    });
  })();

  /* ---------------- Dashboard KPIs ---------------- */
  function renderDashboard(){
    var grid = document.getElementById("kpiGrid");
    grid.innerHTML =
      '<div class="kpi-card total"><div class="kpi-top"><span class="kpi-label">Total points</span><span class="kpi-icon total">▣</span></div><p class="kpi-value">' + fmtInt(STATS.totalPoints) + '</p><div class="kpi-sub">cleaned GSI sample points, V1 model</div></div>' +
      '<div class="kpi-card low"><div class="kpi-top"><span class="kpi-label">Low</span><span class="kpi-icon low">●</span></div><p class="kpi-value low">' + fmtInt(STATS.low) + '</p><div class="kpi-sub">risk score 0–25</div></div>' +
      '<div class="kpi-card moderate"><div class="kpi-top"><span class="kpi-label">Moderate</span><span class="kpi-icon moderate">◆</span></div><p class="kpi-value moderate">' + fmtInt(STATS.moderate) + '</p><div class="kpi-sub">risk score 25–50</div></div>' +
      '<div class="kpi-card high"><div class="kpi-top"><span class="kpi-label">High</span><span class="kpi-icon high">▲</span></div><p class="kpi-value high">' + fmtInt(STATS.high) + '</p><div class="kpi-sub">risk score 50–75</div></div>' +
      '<div class="kpi-card veryhigh"><div class="kpi-top"><span class="kpi-label">Very High</span><span class="kpi-icon veryhigh">⛔</span></div><p class="kpi-value veryhigh">' + fmtInt(STATS.veryHigh) + '</p><div class="kpi-sub">risk score 75–100</div></div>';

    document.getElementById("dashPositives").textContent = fmtInt(STATS.positives) + " points";
    document.getElementById("dashNegatives").textContent = fmtInt(STATS.negatives) + " points";
    document.getElementById("dashStates").textContent = STATS.statesCovered + " states/UTs";
  }

  /* ---------------- shared point-row rendering ---------------- */
  function pointRowHtml(idx){
    var p = POINTS[idx];
    var band = bandKey(p[C.label]);
    return '<div class="point-row" data-idx="' + idx + '">' +
      '<div><div class="pr-loc">' + p[C.state] + '</div><div class="pr-sub">' + p[C.lat].toFixed(4) + ', ' + p[C.lon].toFixed(4) + '</div></div>' +
      '<div><span class="badge ' + band + '">' + fmt1(p[C.score]) + '</span></div>' +
      '<div>' + bandTitle(p[C.label]) + '</div>' +
      '<div>' + (p[C.event] === 1 ? "Documented" : "Background") + '</div>' +
      '<div>' + p[C.density] + ' /10km</div>' +
    '</div>';
  }

  /* ---------------- drawer ---------------- */
  var drawerOverlay = document.getElementById("drawerOverlay");
  var drawer = document.getElementById("drawer");
  function openDrawer(idx){
    var p = POINTS[idx];
    var band = bandKey(p[C.label]);
    drawer.innerHTML =
      '<span class="drawer-close" id="drawerCloseBtn">&times;</span>' +
      '<span class="badge ' + band + '">' + bandTitle(p[C.label]) + '</span>' +
      '<h2 style="margin-top:10px; font-size:17px;">' + p[C.state] + '</h2>' +
      '<div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">' + p[C.lat].toFixed(5) + ', ' + p[C.lon].toFixed(5) + '</div>' +

      '<div class="drawer-section-label">Location</div>' +
      '<div class="detail-grid">' +
        '<div class="detail-item"><div class="dl">State</div><div class="dv" style="font-family:var(--font-body); font-size:13px;">' + p[C.state] + '</div></div>' +
        '<div class="detail-item"><div class="dl">District</div><div class="dv" style="font-family:var(--font-body); font-size:13px;">Data unavailable</div></div>' +
        '<div class="detail-item"><div class="dl">Latitude</div><div class="dv">' + p[C.lat].toFixed(5) + '</div></div>' +
        '<div class="detail-item"><div class="dl">Longitude</div><div class="dv">' + p[C.lon].toFixed(5) + '</div></div>' +
      '</div>' +

      '<div class="drawer-section-label">Risk</div>' +
      '<div class="detail-grid">' +
        '<div class="detail-item"><div class="dl">Risk score</div><div class="dv">' + fmt1(p[C.score]) + '</div></div>' +
        '<div class="detail-item"><div class="dl">Risk level</div><div class="dv">' + bandTitle(p[C.label]) + '</div></div>' +
        '<div class="detail-item"><div class="dl">GSI / event label</div><div class="dv" style="font-size:13px;">' + (p[C.event] === 1 ? "Documented event" : "Background point") + '</div></div>' +
      '</div>' +

      '<div class="drawer-section-label">Terrain</div>' +
      '<div class="detail-grid">' +
        '<div class="detail-item"><div class="dl">Elevation</div><div class="dv">' + fmt1(p[C.elevation]) + ' m</div></div>' +
        '<div class="detail-item"><div class="dl">Slope</div><div class="dv">' + fmt1(p[C.slope]) + '&deg;</div></div>' +
      '</div>' +

      '<div class="drawer-section-label">Historical</div>' +
      '<div class="detail-grid">' +
        '<div class="detail-item"><div class="dl">Historical density (10km)</div><div class="dv">' + p[C.density] + '</div></div>' +
        '<div class="detail-item"><div class="dl">Historical distance</div><div class="dv">' + fmt1(p[C.distance]) + ' km</div></div>' +
      '</div>' +

      '<div class="drawer-section-label">Model</div>' +
      '<div class="info-grid">' +
        '<div class="info-item"><div class="il">Model</div><div class="iv">XGBoost binary classifier</div></div>' +
        '<div class="info-item"><div class="il">Features used</div><div class="iv">elevation_m, slope_deg, historical_landslide_density, historical_landslide_distance</div></div>' +
      '</div>';
    document.getElementById("drawerCloseBtn").addEventListener("click", closeDrawer);
    drawerOverlay.classList.add("open");
  }
  function closeDrawer(){ drawerOverlay.classList.remove("open"); }
  drawerOverlay.addEventListener("click", function(e){ if(e.target === drawerOverlay) closeDrawer(); });
  function bindRowClicks(container){
    container.querySelectorAll(".point-row").forEach(function(row){
      row.addEventListener("click", function(){ openDrawer(parseInt(row.getAttribute("data-idx"), 10)); });
    });
  }

  /* ---------------- Risk Map (interactive Leaflet map) ---------------- */
  var BAND_COLOR = { LOW: "#3E8E5B", MODERATE: "#C9922A", HIGH: "#D97223", "VERY HIGH": "#B93A2E" };
  var riskMapInstance = null;
  var fullBounds = null; // set once on init, used by Reset View

  // Real-world reference geography for the map's location navigator.
  // These are geographic reference points only (state/city centers) — NOT
  // model output. They are used purely to pan/zoom the existing map; no
  // risk score, marker, or data point is invented for any of them.
  var STATE_VIEWS = {
    "Arunachal Pradesh": { center:[27.6,94.2], zoom:7 },
    "Assam": { center:[26.2,92.9], zoom:7 },
    "Himachal Pradesh": { center:[31.8,77.2], zoom:8 },
    "Jammu & Kashmir": { center:[34.0,76.5], zoom:7 },
    "Karnataka": { center:[15.3,75.7], zoom:7 },
    "Kerala": { center:[10.3,76.3], zoom:7 },
    "Maharashtra": { center:[19.6,75.3], zoom:7 },
    "Manipur": { center:[24.8,93.9], zoom:8 },
    "Meghalaya": { center:[25.5,91.3], zoom:8 },
    "Mizoram": { center:[23.3,92.8], zoom:8 },
    "Nagaland": { center:[26.2,94.5], zoom:8 },
    "Sikkim": { center:[27.6,88.5], zoom:9 },
    "Tamil Nadu": { center:[11.1,78.7], zoom:7 },
    "Tripura": { center:[23.9,91.6], zoom:8 },
    "Uttarakhand": { center:[30.1,79.2], zoom:8 },
    "West Bengal": { center:[23.7,87.5], zoom:7 }
  };
  var CITY_DATA = {
    "Sikkim": [["Gangtok",27.3389,88.6065],["Namchi",27.1667,88.3667],["Gyalshing",27.2833,88.2167],["Mangan",27.5167,88.5333],["Pakyong",27.2333,88.6167],["Soreng",27.15,88.15]],
    "Assam": [["Guwahati",26.1445,91.7362],["Dibrugarh",27.4728,94.9120],["Silchar",24.8333,92.7789],["Tezpur",26.6338,92.8000]],
    "Meghalaya": [["Shillong",25.5788,91.8933],["Sohra / Cherrapunji",25.2843,91.7323],["Tura",25.5138,90.2033],["Jowai",25.4500,92.2000]],
    "Mizoram": [["Aizawl",23.7271,92.7176],["Lunglei",22.8833,92.7333],["Champhai",23.4667,93.3333]],
    "Nagaland": [["Kohima",25.6751,94.1086],["Dimapur",25.9091,93.7278],["Mokokchung",26.3242,94.5225]],
    "Manipur": [["Imphal",24.8170,93.9368],["Churachandpur",24.3333,93.6833]],
    "Arunachal Pradesh": [["Itanagar",27.0844,93.6053],["Tawang",27.5859,91.8594],["Bomdila",27.2646,92.4159],["Pasighat",28.0667,95.3333]],
    "Tripura": [["Agartala",23.8315,91.2868],["Dharmanagar",24.3667,92.1667],["Udaipur",23.5333,91.4833]],
    "Himachal Pradesh": [["Shimla",31.1048,77.1734],["Manali",32.2432,77.1892]],
    "Jammu & Kashmir": [["Srinagar",34.0837,74.7973],["Jammu",32.7266,74.8570]],
    "Karnataka": [["Bengaluru",12.9716,77.5946],["Mysuru",12.2958,76.6394]],
    "Kerala": [["Thiruvananthapuram",8.5241,76.9366],["Kochi",9.9312,76.2673]],
    "Maharashtra": [["Mumbai",19.0760,72.8777],["Pune",18.5204,73.8567]],
    "Tamil Nadu": [["Chennai",13.0827,80.2707],["Coimbatore",11.0168,76.9558]],
    "Uttarakhand": [["Dehradun",30.3165,78.0322],["Nainital",29.3919,79.4542]],
    "West Bengal": [["Kolkata",22.5726,88.3639],["Darjeeling",27.0410,88.2663]]
  };
  var NEARBY_RADIUS_KM = 25;
  function haversineKm(lat1, lon1, lat2, lon2){
    var R = 6371, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }

  // Minimal popup only: location, risk score, risk level. Full detail is in the side drawer.
  function popupHtml(p){
    var band = bandKey(p[C.label]);
    return '<div style="font-size:12px; line-height:1.75; font-family:var(--font-body); min-width:170px;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:4px;">' +
        '<b style="font-size:13px;">' + p[C.state] + '</b>' +
        '<span class="badge ' + band + '" style="font-size:10.5px; padding:2px 8px;">' + fmt1(p[C.score]) + '</span>' +
      '</div>' +
      '<b>Risk level:</b> ' + bandTitle(p[C.label]) + '<br>' +
      '<span style="color:var(--text-muted); font-size:11px;">Click marker for full details</span>' +
    '</div>';
  }

  function ensureRiskMapInit(){
    if(riskMapInstance || typeof L === "undefined") return;
    var container = document.getElementById("riskMapFull");
    if(!container) return;

    var osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    });
    var satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
      attribution: "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS user community"
    });
    var terrain = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 17,
      subdomains: "abc",
      attribution: 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'
    });

    var map = L.map(container, { center: [21.5, 84.8], zoom: 5, layers: [osm] });
    riskMapInstance = map;

    var bandLayers = {
      LOW: L.layerGroup(),
      MODERATE: L.layerGroup(),
      HIGH: L.layerGroup(),
      "VERY HIGH": L.layerGroup()
    };

    var minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
    POINTS.forEach(function(p, i){
      var lat = p[C.lat], lon = p[C.lon];
      if(lat < minLat) minLat = lat;
      if(lat > maxLat) maxLat = lat;
      if(lon < minLon) minLon = lon;
      if(lon > maxLon) maxLon = lon;
      var color = BAND_COLOR[p[C.label]] || BAND_COLOR.LOW;
      var marker = L.circleMarker([lat, lon], {
        radius: 4, color: color, weight: 1, fill: true, fillColor: color, fillOpacity: 0.75
      });
      // Minimal Leaflet popup (location / score / level only) — the full
      // detail set lives in the side drawer, opened via the marker click below.
      marker.bindPopup(popupHtml(p), { maxWidth: 280 });
      marker.on("click", function(){ openDrawer(i); });
      marker.addTo(bandLayers[p[C.label]]);
    });
    bandLayers.LOW.addTo(map);
    bandLayers.MODERATE.addTo(map);
    bandLayers.HIGH.addTo(map);
    bandLayers["VERY HIGH"].addTo(map);
    fullBounds = [[minLat, minLon], [maxLat, maxLon]];
    map.fitBounds(fullBounds);

    L.control.layers(
      { "Normal": osm, "Satellite": satellite, "Terrain": terrain },
      { "Low": bandLayers.LOW, "Moderate": bandLayers.MODERATE, "High": bandLayers.HIGH, "Very High": bandLayers["VERY HIGH"] },
      { collapsed: false, position: "topright" }
    ).addTo(map);

    var legend = L.control({ position: "bottomleft" });
    legend.onAdd = function(){
      var div = L.DomUtil.create("div", "map-legend-ctrl");
      var rows = ["LOW", "MODERATE", "HIGH", "VERY HIGH"];
      var html = '<div class="ml-title">Risk category</div>';
      rows.forEach(function(b){
        html += '<div class="ml-row"><span class="ml-dot" style="background:' + BAND_COLOR[b] + ';"></span>' + bandTitle(b) + '</div>';
      });
      html += '<div class="ml-note">Existing GSI sample points.</div>';
      div.innerHTML = html;
      return div;
    };
    legend.addTo(map);

    /* ---------------- state / city location navigator (top-left) ---------------- */
    var highlightLayer = L.layerGroup().addTo(map);
    var navStates = DATA.states.slice().filter(function(s){ return STATE_VIEWS[s]; }).sort();

    var navControl = L.control({ position: "topleft" });
    navControl.onAdd = function(){
      var div = L.DomUtil.create("div", "map-locnav-ctrl");
      div.innerHTML =
        '<div class="ln-header">' +
          '<span class="ln-title" id="navTitle">Jump to location</span>' +
          '<button type="button" id="navCollapseBtn" class="ln-collapse-btn" title="Minimize panel" aria-label="Minimize jump-to-location panel">&#9662;</button>' +
        '</div>' +
        '<div class="ln-body" id="navBody">' +
          '<label class="ln-label" for="navStateSel">State</label>' +
          '<select id="navStateSel" class="ln-select"><option value="">Select State</option>' +
            navStates.map(function(s){ return '<option value="' + s + '">' + s + '</option>'; }).join("") +
          '</select>' +
          '<label class="ln-label" for="navCitySel">City / Area</label>' +
          '<select id="navCitySel" class="ln-select" disabled><option value="">Select City / Area</option></select>' +
          '<button type="button" id="navResetBtn" class="ln-reset-btn">↺ Reset View</button>' +
          '<div id="navStatusMsg" class="ln-status"></div>' +
        '</div>';
      // Prevent map drag/zoom/scroll from hijacking clicks inside the control.
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      return div;
    };
    navControl.addTo(map);

    setTimeout(function(){
      var stateSel = document.getElementById("navStateSel");
      var citySel = document.getElementById("navCitySel");
      var resetBtn = document.getElementById("navResetBtn");
      var statusMsg = document.getElementById("navStatusMsg");
      var collapseBtn = document.getElementById("navCollapseBtn");
      var navTitle = document.getElementById("navTitle");
      var navCtrlEl = collapseBtn ? collapseBtn.closest(".map-locnav-ctrl") : null;
      if(!stateSel || !citySel || !resetBtn) return;

      if(collapseBtn && navCtrlEl){
        collapseBtn.addEventListener("click", function(){
          var collapsed = navCtrlEl.classList.toggle("collapsed");
          collapseBtn.innerHTML = collapsed ? "&#9656;" : "&#9662;";
          collapseBtn.title = collapsed ? "Expand panel" : "Minimize panel";
          collapseBtn.setAttribute("aria-label", collapsed ? "Expand jump-to-location panel" : "Minimize jump-to-location panel");
          navTitle.textContent = collapsed ? "⌖ Location" : "Jump to location";
        });
      }

      function clearHighlight(){ highlightLayer.clearLayers(); }

      stateSel.addEventListener("change", function(){
        clearHighlight();
        statusMsg.textContent = "";
        var st = stateSel.value;
        citySel.innerHTML = '<option value="">Select City / Area</option>';
        if(!st){
          citySel.disabled = true;
          return;
        }
        var cities = CITY_DATA[st] || [];
        cities.forEach(function(c){
          var opt = document.createElement("option");
          opt.value = c[0]; opt.textContent = c[0];
          citySel.appendChild(opt);
        });
        citySel.disabled = cities.length === 0;
        var view = STATE_VIEWS[st];
        if(view) map.setView(view.center, view.zoom);
      });

      citySel.addEventListener("change", function(){
        clearHighlight();
        var st = stateSel.value;
        var cityName = citySel.value;
        if(!st || !cityName) { statusMsg.textContent = ""; return; }
        var cities = CITY_DATA[st] || [];
        var city = cities.filter(function(c){ return c[0] === cityName; })[0];
        if(!city) return;
        var lat = city[1], lon = city[2];
        map.setView([lat, lon], 11);

        // Find any real model points within NEARBY_RADIUS_KM — never fabricated.
        var nearby = [];
        POINTS.forEach(function(p, i){
          if(p[C.state] !== st) return;
          if(haversineKm(lat, lon, p[C.lat], p[C.lon]) <= NEARBY_RADIUS_KM) nearby.push(i);
        });
        L.circle([lat, lon], {
          radius: NEARBY_RADIUS_KM * 1000, color: "#33553F",
          weight: 1.5, dashArray: "4,5", fill: false, opacity: 0.6
        }).addTo(highlightLayer);
        nearby.forEach(function(i){
          var p = POINTS[i];
          L.circleMarker([p[C.lat], p[C.lon]], {
            radius: 8, color: "#33553F", weight: 2, fill: true, fillColor: BAND_COLOR[p[C.label]], fillOpacity: 0.9
          }).addTo(highlightLayer);
        });
        statusMsg.textContent = nearby.length > 0
          ? nearby.length + " model point" + (nearby.length === 1 ? "" : "s") + " found within " + NEARBY_RADIUS_KM + "km of " + cityName + "."
          : "No documented model points within " + NEARBY_RADIUS_KM + "km of " + cityName + " — showing geographic location only.";
      });

      resetBtn.addEventListener("click", function(){
        stateSel.value = "";
        citySel.innerHTML = '<option value="">Select City / Area</option>';
        citySel.disabled = true;
        statusMsg.textContent = "";
        clearHighlight();
        if(fullBounds) map.fitBounds(fullBounds);
      });
    }, 0);
  }

  /* ---------------- Location details (Risk Map page) ---------------- */
  var PAGE_SIZE = 50;
  var locFiltered = [];
  var locShown = 0;

  function computeLocFiltered(){
    var q = document.getElementById("locSearch").value.trim().toLowerCase();
    var band = document.getElementById("locBandFilter").value;
    var st = document.getElementById("locStateFilter").value;
    var idxs = [];
    for(var i = 0; i < POINTS.length; i++){
      var p = POINTS[i];
      if(band !== "all" && p[C.label] !== band) continue;
      if(st !== "all" && p[C.state] !== st) continue;
      if(q && p[C.state].toLowerCase().indexOf(q) === -1) continue;
      idxs.push(i);
    }
    idxs.sort(function(a, b){ return POINTS[b][C.score] - POINTS[a][C.score]; });
    return idxs;
  }
  function renderLocList(reset){
    if(reset){ locFiltered = computeLocFiltered(); locShown = 0; }
    var list = document.getElementById("locList");
    var next = Math.min(locShown + PAGE_SIZE, locFiltered.length);
    var html = "";
    for(var i = locShown; i < next; i++){ html += pointRowHtml(locFiltered[i]); }
    if(reset){ list.innerHTML = html; } else { list.insertAdjacentHTML("beforeend", html); }
    bindRowClicks(list);
    locShown = next;
    document.getElementById("locResultCount").textContent =
      fmtInt(locFiltered.length) + " matching point" + (locFiltered.length === 1 ? "" : "s") +
      " · showing " + fmtInt(locShown);
    document.getElementById("locLoadMore").style.display = locShown >= locFiltered.length ? "none" : "inline-block";
  }
  document.getElementById("locSearch").addEventListener("input", function(){ renderLocList(true); });
  document.getElementById("locBandFilter").addEventListener("change", function(){ renderLocList(true); });
  document.getElementById("locStateFilter").addEventListener("change", function(){ renderLocList(true); });
  document.getElementById("locLoadMore").addEventListener("click", function(){ renderLocList(false); });

  function populateStateFilter(){
    var sel = document.getElementById("locStateFilter");
    DATA.states.forEach(function(s){
      var opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      sel.appendChild(opt);
    });
  }

  /* ---------------- Alerts page ---------------- */
  var alertFiltered = [];
  var alertShown = 0;
  function computeAlertFiltered(){
    var q = document.getElementById("alertSearch").value.trim().toLowerCase();
    var band = document.getElementById("alertBandFilter").value;
    var idxs = [];
    for(var i = 0; i < POINTS.length; i++){
      var p = POINTS[i];
      var isElevated = p[C.label] === "HIGH" || p[C.label] === "VERY HIGH";
      if(band === "elevated" && !isElevated) continue;
      if(band !== "elevated" && p[C.label] !== band) continue;
      if(q && p[C.state].toLowerCase().indexOf(q) === -1) continue;
      idxs.push(i);
    }
    idxs.sort(function(a, b){ return POINTS[b][C.score] - POINTS[a][C.score]; });
    return idxs;
  }
  function renderAlertList(reset){
    if(reset){ alertFiltered = computeAlertFiltered(); alertShown = 0; }
    var list = document.getElementById("alertList");
    var next = Math.min(alertShown + PAGE_SIZE, alertFiltered.length);
    var html = "";
    for(var i = alertShown; i < next; i++){ html += pointRowHtml(alertFiltered[i]); }
    if(reset){ list.innerHTML = html; } else { list.insertAdjacentHTML("beforeend", html); }
    bindRowClicks(list);
    alertShown = next;
    document.getElementById("alertResultCount").textContent =
      fmtInt(alertFiltered.length) + " matching point" + (alertFiltered.length === 1 ? "" : "s") +
      " · showing " + fmtInt(alertShown);
    document.getElementById("alertLoadMore").style.display = alertShown >= alertFiltered.length ? "none" : "inline-block";
  }
  document.getElementById("alertSearch").addEventListener("input", function(){ renderAlertList(true); });
  document.getElementById("alertBandFilter").addEventListener("change", function(){ renderAlertList(true); });
  document.getElementById("alertLoadMore").addEventListener("click", function(){ renderAlertList(false); });

  function renderAlertKpis(){
    var grid = document.getElementById("alertKpiGrid");
    grid.innerHTML =
      '<div class="kpi-card high"><div class="kpi-top"><span class="kpi-label">High</span><span class="kpi-icon high">▲</span></div><p class="kpi-value high">' + fmtInt(STATS.high) + '</p><div class="kpi-sub">risk score 50–75</div></div>' +
      '<div class="kpi-card veryhigh"><div class="kpi-top"><span class="kpi-label">Very High</span><span class="kpi-icon veryhigh">⛔</span></div><p class="kpi-value veryhigh">' + fmtInt(STATS.veryHigh) + '</p><div class="kpi-sub">risk score 75–100</div></div>' +
      '<div class="kpi-card total"><div class="kpi-top"><span class="kpi-label">Total elevated</span><span class="kpi-icon total">◎</span></div><p class="kpi-value">' + fmtInt(STATS.high + STATS.veryHigh) + '</p><div class="kpi-sub">of ' + fmtInt(STATS.totalPoints) + ' sample points</div></div>';
  }

  /* ---------------- Field report ---------------- */
  function initFieldReport(){
    var stateSel = document.getElementById("frState");
    stateSel.innerHTML = DATA.states.map(function(s){ return '<option value="' + s + '">' + s + '</option>'; }).join("");

    var selectedType = null;
    document.querySelectorAll(".obs-type-opt").forEach(function(opt){
      opt.addEventListener("click", function(){
        document.querySelectorAll(".obs-type-opt").forEach(function(o){ o.classList.remove("selected"); });
        opt.classList.add("selected");
        selectedType = opt.getAttribute("data-val");
      });
    });

    var locCaptured = document.getElementById("locationCaptured");
    document.getElementById("btnUseLocation").addEventListener("click", function(){
      var btn = this;
      if(!navigator.geolocation){
        locCaptured.style.display = "block";
        locCaptured.textContent = "Geolocation not available in this browser.";
        return;
      }
      btn.textContent = "◎ Locating…";
      navigator.geolocation.getCurrentPosition(function(pos){
        btn.textContent = "◎ Location captured";
        locCaptured.style.display = "block";
        locCaptured.textContent = "Captured: " + pos.coords.latitude.toFixed(5) + ", " + pos.coords.longitude.toFixed(5) + " (used for this field report only)";
      }, function(){
        btn.textContent = "◎ Use current location";
        locCaptured.style.display = "block";
        locCaptured.textContent = "Location permission denied or unavailable.";
      });
    });

    var fileInput = document.getElementById("frImageInput");
    var uploadZoneText = document.getElementById("uploadZoneText");
    var uploadError = document.getElementById("uploadError");
    var previewBlock = document.getElementById("imagePreviewBlock");
    var previewThumb = document.getElementById("imagePreviewThumb");
    var fileInfoName = document.getElementById("fileInfoName");
    var fileInfoType = document.getElementById("fileInfoType");
    var fileInfoSize = document.getElementById("fileInfoSize");
    var aiPreview = document.getElementById("aiVerificationPreview");
    var btnRemoveImage = document.getElementById("btnRemoveImage");
    var currentObjectUrl = null;
    var UPLOAD_ZONE_DEFAULT_TEXT = "＋ Upload field evidence (JPG, JPEG, PNG or WEBP)";
    var ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
    var MAX_IMAGE_BYTES = 10 * 1024 * 1024;

    function formatBytes(bytes){
      if(bytes < 1024) return bytes + " B";
      if(bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }
    function resetImageSelection(){
      if(currentObjectUrl){ URL.revokeObjectURL(currentObjectUrl); currentObjectUrl = null; }
      if(fileInput) fileInput.value = "";
      if(uploadZoneText) uploadZoneText.textContent = UPLOAD_ZONE_DEFAULT_TEXT;
      if(previewBlock) previewBlock.style.display = "none";
      if(aiPreview) aiPreview.style.display = "none";
    }
    if(fileInput){
      fileInput.addEventListener("change", function(){
        var file = fileInput.files && fileInput.files[0];
        if(!file) return;
        if(uploadError) uploadError.style.display = "none";
        if(ALLOWED_IMAGE_TYPES.indexOf(file.type) === -1){
          resetImageSelection();
          if(uploadError){ uploadError.textContent = "Unsupported image format. Please choose JPG, JPEG, PNG, or WEBP."; uploadError.style.display = "block"; }
          return;
        }
        if(file.size > MAX_IMAGE_BYTES){
          resetImageSelection();
          if(uploadError){ uploadError.textContent = "File is too large (max 10 MB). Please choose a smaller image."; uploadError.style.display = "block"; }
          return;
        }
        if(currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = URL.createObjectURL(file);
        if(uploadZoneText) uploadZoneText.textContent = "✓ " + file.name;
        if(previewThumb) previewThumb.src = currentObjectUrl;
        if(fileInfoName) fileInfoName.textContent = file.name;
        if(fileInfoType) fileInfoType.textContent = file.type || "Unknown";
        if(fileInfoSize) fileInfoSize.textContent = formatBytes(file.size);
        if(previewBlock) previewBlock.style.display = "flex";
        if(aiPreview) aiPreview.style.display = "block";
      });
    }
    if(btnRemoveImage){
      btnRemoveImage.addEventListener("click", function(){ resetImageSelection(); if(uploadError) uploadError.style.display = "none"; });
    }
    document.getElementById("btnSubmitReport").addEventListener("click", function(){
      document.getElementById("reportSuccess").style.display = "flex";
    });
  }

  /* ---------------- Analytics ---------------- */
  function renderAnalytics(){
    var bandCtx = document.getElementById("chartBands").getContext("2d");
    new Chart(bandCtx, {
      type: "bar",
      data: {
        labels: ["Low", "Moderate", "High", "Very High"],
        datasets: [{
          data: [STATS.low, STATS.moderate, STATS.high, STATS.veryHigh],
          backgroundColor: ["#3E8E5B", "#C9922A", "#D97223", "#B93A2E"],
          borderRadius: 4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, grid: { color: "#ECEBE4" } }, x: { grid: { display: false } } }
      }
    });

    var classCtx = document.getElementById("chartClass").getContext("2d");
    new Chart(classCtx, {
      type: "doughnut",
      data: {
        labels: ["Documented landslide (" + fmtInt(STATS.positives) + ")", "Background point (" + fmtInt(STATS.negatives) + ")"],
        datasets: [{
          data: [STATS.positives, STATS.negatives],
          backgroundColor: ["#33553F", "#CFCEC5"]
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } }
      }
    });

    var stateList = document.getElementById("stateBarList");
    var maxCount = DATA.stateCounts[0][1];
    stateList.innerHTML = DATA.stateCounts.map(function(sc){
      var pct = Math.round((sc[1] / maxCount) * 100);
      return '<div class="state-bar-row">' +
        '<div class="state-bar-name">' + sc[0] + '</div>' +
        '<div class="state-bar-track"><div class="state-bar-fill" style="width:' + pct + '%;"></div></div>' +
        '<div class="state-bar-value">' + fmtInt(sc[1]) + '</div>' +
      '</div>';
    }).join("");
  }

  /* ---------------- About page ---------------- */
  var FEATURE_IMPORTANCE = [
    ["historical_landslide_distance", 0.7282],
    ["historical_landslide_density", 0.1820],
    ["slope_deg", 0.0453],
    ["elevation_m", 0.0445]
  ];
  function renderAbout(){
    var statesEl = document.getElementById("aboutStates");
    if(statesEl) statesEl.textContent = STATS.statesCovered + " states/UTs";
    var fiList = document.getElementById("featureImportanceList");
    if(fiList){
      var maxImp = FEATURE_IMPORTANCE[0][1];
      fiList.innerHTML = FEATURE_IMPORTANCE.map(function(f){
        var pct = Math.round((f[1] / maxImp) * 100);
        return '<div class="state-bar-row">' +
          '<div class="state-bar-name" style="width:200px;">' + f[0] + '</div>' +
          '<div class="state-bar-track"><div class="state-bar-fill" style="width:' + pct + '%;"></div></div>' +
          '<div class="state-bar-value">' + f[1].toFixed(4) + '</div>' +
        '</div>';
      }).join("");
    }
  }

  /* ---------------- init ---------------- */
  renderDashboard();
  populateStateFilter();
  renderLocList(true);
  renderAlertKpis();
  renderAlertList(true);
  initFieldReport();
  renderAnalytics();
  renderAbout();
})();
