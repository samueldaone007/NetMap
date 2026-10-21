(function () {
  "use strict";

  const dataElement = document.getElementById("topology-data");
  const container = document.getElementById("topology-canvas");
  if (!dataElement || !container || typeof window.cytoscape !== "function") return;

  const data = JSON.parse(dataElement.textContent);
  const root = document.getElementById("topology-root");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const hatchSvg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">' +
    '<path d="M-2 2L2-2M0 8L8 0M6 10L10 6" stroke="#2B2622" stroke-width="1.15" opacity=".45"/>' +
    "</svg>";
  const HATCH = 'url("data:image/svg+xml;utf8,' + encodeURIComponent(hatchSvg) + '")';

  const elements = [
    ...data.nodes.map((node) => ({
      data: node,
      classes: [
        node.kind === "unknown" ? "unknown" : node.type,
        node.outage ? "outage" : "",
        node.needs_identifying ? "needs-identifying" : "",
      ]
        .filter(Boolean)
        .join(" "),
    })),
    ...data.edges.map((edge) => ({
      data: edge,
      classes: [edge.unknown ? "unknown" : "", edge.outage ? "outage" : ""]
        .filter(Boolean)
        .join(" "),
    })),
  ];

  const cy = window.cytoscape({
    container: container,
    elements: elements,
    minZoom: 0.12,
    maxZoom: 3.2,
    wheelSensitivity: 0.22,
    boxSelectionEnabled: false,
    selectionType: "single",
    style: [
      {
        selector: "node",
        style: {
          shape: "round-rectangle",
          width: 58,
          height: 30,
          "background-color": "#FAF6EE",
          "border-color": "#2B2622",
          "border-width": 1.5,
          label: "data(label)",
          color: "#2B2622",
          "font-family": '"Bricolage Grotesque", "Trebuchet MS", sans-serif',
          "font-size": 9,
          "font-weight": 600,
          "text-valign": "bottom",
          "text-halign": "center",
          "text-margin-y": 7,
          "text-max-width": 118,
          "text-wrap": "ellipsis",
          "text-background-color": "#F3EDE2",
          "text-background-opacity": 0.9,
          "text-background-padding": 2,
          "min-zoomed-font-size": 6,
          "overlay-opacity": 0,
          "transition-property": "opacity, border-width, border-color",
          "transition-duration": reduceMotion ? "0s" : "140ms",
        },
      },
      {
        selector: 'node[type="switch"]',
        style: { width: 62, height: 26, "background-color": "#F4E3B9" },
      },
      {
        selector: 'node[type="server"]',
        style: { "background-color": "#D9E2F1" },
      },
      {
        selector: 'node[type="router"]',
        style: {
          shape: "hexagon",
          width: 56,
          height: 38,
          "background-color": "#DDE6CF",
        },
      },
      {
        selector: 'node[type="firewall"]',
        style: {
          shape: "octagon",
          width: 46,
          height: 38,
          "background-color": "#E9D8E4",
        },
      },
      {
        selector: 'node[type="ap"]',
        style: { shape: "ellipse", width: 38, height: 34, "background-color": "#DDE6CF" },
      },
      {
        selector: 'node[type="patch_panel"]',
        style: { width: 70, height: 22, "background-color": "#E9E0D1" },
      },
      {
        selector: 'node[type="external"]',
        style: {
          shape: "tag",
          width: 64,
          height: 32,
          "background-color": "#F4E3B9",
        },
      },
      {
        selector: "node.needs-identifying",
        style: { "border-style": "dashed", "border-width": 2 },
      },
      {
        selector: "node.outage",
        style: {
          "background-image": HATCH,
          "background-fit": "none",
          "background-repeat": "repeat",
          "background-width": "8px",
          "background-height": "8px",
          "border-color": "#7B3F6E",
          "border-width": 2.5,
        },
      },
      {
        selector: "node.unknown",
        style: {
          shape: "diamond",
          width: 26,
          height: 26,
          label: "?",
          "background-color": "#7B3F6E",
          color: "#FAF6EE",
          "font-size": 11,
          "font-weight": 700,
          "border-style": "dashed",
          "border-color": "#7B3F6E",
          "text-valign": "bottom",
          "text-margin-y": 6,
          "text-background-opacity": 0,
        },
      },
      {
        selector: "node.unknown:selected",
        style: { "border-color": "#2B2622", "border-width": 2 },
      },
      {
        selector: "node.selected",
        style: {
          "border-color": "#2F5DA8",
          "border-width": 3,
          "overlay-color": "#2F5DA8",
          "overlay-opacity": 0.08,
          "overlay-padding": 6,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#746A5F",
          "curve-style": "bezier",
          "target-arrow-shape": "none",
          label: "data(label)",
          color: "#746A5F",
          "font-family": '"IBM Plex Mono", "Cascadia Mono", monospace',
          "font-size": 6.5,
          "text-rotation": "autorotate",
          "text-background-color": "#F3EDE2",
          "text-background-opacity": 0.9,
          "text-background-padding": 2,
          "text-max-width": 90,
          "min-zoomed-font-size": 5,
          "overlay-opacity": 0,
          "transition-property": "opacity, line-color, width",
          "transition-duration": reduceMotion ? "0s" : "140ms",
        },
      },
      {
        selector: "edge.unknown",
        style: {
          "line-style": "dashed",
          "line-color": "#7B3F6E",
          "line-dash-pattern": [5, 4],
        },
      },
      {
        selector: "edge.outage",
        style: { "line-color": "#7B3F6E", width: 2.8 },
      },
      {
        selector: "edge.selected",
        style: { "line-color": "#2F5DA8", width: 3.2 },
      },
      { selector: ".faded", style: { opacity: 0.14 } },
    ],
  });

  const readout = {
    nodes: document.getElementById("readout-nodes"),
    edges: document.getElementById("readout-edges"),
    unknown: document.getElementById("readout-unknown"),
    outages: document.getElementById("readout-outages"),
  };
  const saveStatus = document.getElementById("save-status");
  const layoutInput = document.getElementById("layout-input");
  const inspector = {
    empty: document.getElementById("inspector-empty"),
    content: document.getElementById("inspector-content"),
    type: document.getElementById("inspector-type"),
    name: document.getElementById("inspector-name"),
    status: document.getElementById("inspector-status"),
    deviceType: document.getElementById("inspector-device-type"),
    location: document.getElementById("inspector-location"),
    ip: document.getElementById("inspector-ip"),
    ports: document.getElementById("inspector-ports"),
    source: document.getElementById("inspector-source"),
    outage: document.getElementById("inspector-outage"),
    outageCause: document.getElementById("inspector-outage-cause"),
    link: document.getElementById("inspector-link"),
  };

  function setStatus(message, tone) {
    if (!saveStatus) return;
    saveStatus.textContent = message || "";
    saveStatus.dataset.tone = tone || "";
    if (message) {
      window.clearTimeout(setStatus.timer);
      setStatus.timer = window.setTimeout(() => {
        saveStatus.textContent = "";
        saveStatus.dataset.tone = "";
      }, 4200);
    }
  }

  function updateReadout() {
    if (!readout.nodes) return;
    const deviceNodes = cy.nodes('[kind="device"]');
    const edges = cy.edges();
    const unknown = cy.nodes(".unknown");
    const outages = cy.nodes(".outage").filter('[kind="device"]');
    readout.nodes.textContent = deviceNodes.length;
    readout.edges.textContent = edges.length;
    readout.unknown.textContent = unknown.length;
    readout.outages.textContent = outages.length;
  }

  function anchorUnknownNodes() {
    cy.nodes(".unknown").forEach((node, index) => {
      const edge = node.connectedEdges()[0];
      if (!edge) return;
      const source = edge.source().position();
      node.position({
        x: source.x + 138 + (index % 3) * 18,
        y: source.y + 62 + (index % 5) * 14,
      });
    });
  }

  function fitGraph() {
    if (!cy.elements().length) return;
    cy.fit(cy.elements(), 46);
  }

  function setLayoutButtons(name) {
    document.querySelectorAll(".layout-button").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.layout === name);
    });
    if (layoutInput) layoutInput.value = name;
    const url = new URL(window.location.href);
    url.searchParams.set("layout", name);
    window.history.replaceState(null, "", url.toString());
  }

  function placeSavedLayout() {
    const deviceNodes = cy.nodes('[kind="device"]');
    const saved = deviceNodes.filter((node) => {
      const x = Number(node.data("x"));
      const y = Number(node.data("y"));
      return Number.isFinite(x) && Number.isFinite(y) && (x !== 0 || y !== 0);
    });
    if (!saved.length) {
      setStatus("No saved positions yet — run a layout, then keep it.", "warning");
      applyLayout("cose");
      return;
    }
    saved.forEach((node) => {
      node.position({ x: Number(node.data("x")), y: Number(node.data("y")) });
    });
    const savedIds = new Set(saved.map((node) => node.id()));
    const missing = deviceNodes.filter((node) => !savedIds.has(node.id()));
    if (missing.length) {
      const xs = saved.map((node) => node.position("x"));
      const ys = saved.map((node) => node.position("y"));
      const startX = Math.max(...xs) + 120;
      const startY = Math.min(...ys);
      missing.forEach((node, index) => {
        node.position({ x: startX + (index % 3) * 92, y: startY + Math.floor(index / 3) * 70 });
      });
      setStatus(`${missing.length} unplaced device(s) parked to the right.`, "warning");
    }
    cy.one("layoutstop", () => {
      anchorUnknownNodes();
      fitGraph();
      updateReadout();
    });
    cy.layout({ name: "preset", fit: false, padding: 46 }).run();
  }

  function applyLayout(name) {
    setLayoutButtons(name);
    cy.elements().removeClass("selected faded");
    if (name === "saved") {
      placeSavedLayout();
      return;
    }
    const options = {
      name: name,
      animate: !reduceMotion,
      animationDuration: 260,
      fit: false,
      padding: 46,
    };
    if (name === "cose") {
      options.idealEdgeLength = 110;
      options.nodeRepulsion = 340000;
      options.gravity = 70;
      options.numIter = 700;
    }
    if (name === "breadthfirst") {
      options.directed = false;
      options.spacingFactor = 1.1;
    }
    if (name === "concentric") {
      options.minNodeSpacing = 46;
    }
    if (name === "grid") {
      options.avoidOverlap = true;
      options.condense = false;
    }
    cy.one("layoutstop", () => {
      anchorUnknownNodes();
      fitGraph();
      updateReadout();
    });
    cy.layout(options).run();
  }

  function selectNode(node) {
    cy.elements().removeClass("selected faded").addClass("faded");
    node.removeClass("faded").addClass("selected");
    node.connectedEdges().removeClass("faded").addClass("selected");
    node.connectedEdges().connectedNodes().removeClass("faded");
    node.removeClass("faded");
    showInspector(node.data());
  }

  function clearSelection() {
    cy.elements().removeClass("selected faded");
    inspector.empty.hidden = false;
    inspector.content.hidden = true;
    if (inspector.type) inspector.type.textContent = "station";
  }

  function showInspector(node) {
    inspector.empty.hidden = true;
    inspector.content.hidden = false;
    inspector.type.textContent = node.kind === "unknown" ? "untraced" : "station";
    if (node.kind === "unknown") {
      inspector.name.textContent = "Unknown far end";
      inspector.status.textContent = "Untraced";
      inspector.status.className = "badge badge-flag";
      inspector.deviceType.textContent = "Ghost node";
      inspector.location.textContent = node.detail || "—";
      inspector.ip.textContent = "—";
      inspector.ports.textContent = "—";
      inspector.source.textContent = "Not recorded yet";
      inspector.outage.hidden = true;
      inspector.link.hidden = true;
      inspector.link.removeAttribute("href");
      return;
    }
    inspector.name.textContent = node.name;
    inspector.status.textContent = node.status_label;
    inspector.status.className = "badge badge-" + (node.status || "unknown");
    inspector.deviceType.textContent = node.type_label;
    inspector.location.textContent = node.location || "Unplaced";
    inspector.ip.textContent = node.management_ip || "—";
    inspector.ports.textContent = `${node.ports_used} used / ${node.ports_total} total`;
    inspector.source.textContent = node.source;
    inspector.outage.hidden = !node.outage;
    inspector.outageCause.textContent = node.outage_cause || "";
    inspector.link.hidden = false;
    inspector.link.href = node.url;
  }

  document.querySelectorAll(".layout-button").forEach((button) => {
    button.addEventListener("click", () => applyLayout(button.dataset.layout));
  });

  cy.on("tap", "node", (event) => selectNode(event.target));
  cy.on("tap", (event) => {
    if (event.target === cy) clearSelection();
  });
  cy.on("drag", "node", () => {
    setStatus("Layout changed — keep it when ready.", "dirty");
  });
  cy.on("dblclick", "node", (event) => {
    const node = event.target;
    if (node.data("kind") === "unknown") return;
    if (node.data("url")) window.location.href = node.data("url");
  });

  const saveButton = document.getElementById("save-layout");
  if (saveButton) {
    saveButton.addEventListener("click", async () => {
      const positions = {};
      cy.nodes('[kind="device"]').forEach((node) => {
        const position = node.position();
        positions[node.id()] = { x: position.x, y: position.y };
      });
      if (!Object.keys(positions).length) return;
      saveButton.disabled = true;
      setStatus("Keeping positions…", "saving");
      try {
        const token = document.querySelector('meta[name="csrf-token"]').content;
        const response = await fetch(data.saveUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
          },
          body: JSON.stringify({ positions: positions }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Could not save the layout.");
        }
        setStatus(`Saved ${payload.saved} station position${payload.saved === 1 ? "" : "s"}.`, "ok");
      } catch (error) {
        setStatus(error.message || "Could not save the layout.", "error");
      } finally {
        saveButton.disabled = false;
      }
    });
  }

  const pngButton = document.getElementById("download-png");
  if (pngButton) {
    pngButton.addEventListener("click", () => {
      if (!cy.elements().length) return;
      const uri = cy.png({ full: true, scale: 2, bg: "#F3EDE2" });
      const link = document.createElement("a");
      const date = new Date().toISOString().slice(0, 10);
      link.href = uri;
      link.download = `netmap-topology-${date}.png`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    });
  }

  const filterForm = document.getElementById("map-filter-form");
  if (filterForm) {
    filterForm.addEventListener("submit", () => {
      if (layoutInput) layoutInput.value = data.layout || "cose";
    });
  }

  window.addEventListener("resize", () => cy.resize());
  updateReadout();
  if (root && root.dataset.hasNodes === "1") {
    applyLayout(data.layout || "cose");
  }
})();
