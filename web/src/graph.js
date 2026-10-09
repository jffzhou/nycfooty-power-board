import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';

cytoscape.use(dagre);

function mixColor(first, second, amount) {
  const mixed = first.map((channel, index) => Math.round(
    channel + (second[index] - channel) * amount,
  ));
  return `rgb(${mixed.join(', ')})`;
}

function strengthColor(power) {
  const weak = [205, 83, 68];
  const average = [205, 161, 56];
  const strong = [20, 132, 101];
  if (power <= 5) return mixColor(weak, average, Math.max(0, (power - 1) / 4));
  return mixColor(average, strong, Math.min(1, (power - 5) / 5));
}

function renderFlowRanking(graph) {
  const container = document.querySelector('#flow-ranking');
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  container.replaceChildren(...graph.flow.ranking.map((nodeId, index) => {
    const node = nodes.get(nodeId);
    const item = document.createElement('div');
    item.className = 'flow-rank-item';
    const rank = document.createElement('span');
    rank.textContent = String(index + 1).padStart(2, '0');
    const team = document.createElement('strong');
    team.textContent = node.teams.join(' + ');
    const share = document.createElement('b');
    share.textContent = `${(node.flowShare * 100).toFixed(1)}%`;
    item.append(rank, team, share);
    return item;
  }));
}

function renderTopology(graph) {
  const container = document.querySelector('#topology-flow');
  const components = new Map(graph.components.map((component) => [component.id, component]));
  container.replaceChildren(...graph.layers.map((layer, index) => {
    const item = document.createElement('div');
    item.className = 'topology-tier';
    const tier = document.createElement('span');
    tier.textContent = `Tier ${index + 1}`;
    const summary = document.createElement('strong');
    summary.textContent = layer.map((componentId) => {
      const component = components.get(componentId);
      return component.cyclic
        ? `${component.teams.length}-team cycle`
        : component.teams[0];
    }).join(' / ');
    summary.title = layer
      .map((componentId) => components.get(componentId).teams.join(' + '))
      .join(' / ');
    item.append(tier, summary);
    return item;
  }));
}

export function renderResultGraph(graph) {
  const cycleStatus = document.querySelector('#cycle-status');
  const cycleTeamCount = graph.cycles.reduce((count, teams) => count + teams.length, 0);
  cycleStatus.textContent = graph.cycles.length
    ? `${cycleTeamCount}-team competitive cycle`
    : 'No competitive cycles';
  cycleStatus.classList.toggle('warning', graph.cycles.length > 0);

  const elements = [
    ...graph.nodes.map((node) => ({
      data: { ...node, strengthColor: strengthColor(node.power) },
      classes: node.cyclic ? 'cycle-member' : '',
    })),
    ...graph.edges.map((edge) => ({
      data: edge,
      classes: [
        edge.forfeit ? 'administrative' : '',
        edge.tie ? 'tie' : '',
        edge.flowCredit === 0 ? 'zero-flow' : '',
      ]
        .filter(Boolean)
        .join(' '),
    })),
  ];
  const graphView = cytoscape({
    container: document.querySelector('#result-graph'),
    elements,
    pixelRatio: 2,
    motionBlur: false,
    textureOnViewport: false,
    minZoom: 0.45,
    maxZoom: 2.2,
    wheelSensitivity: 0.2,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': 'data(strengthColor)',
          'border-color': 'data(color)',
          'border-width': 3,
          color: '#eef5f2',
          label: 'data(resultLabel)',
          shape: 'round-rectangle',
          width: 'data(resultWidth)',
          height: 'data(resultHeight)',
          'font-size': 12,
          'font-weight': 700,
          'text-wrap': 'wrap',
          'text-max-width': 150,
          'text-valign': 'center',
          'text-halign': 'center',
        },
      },
      {
        selector: 'node.flow-mode',
        style: {
          label: 'data(flowLabel)',
          width: 'data(flowWidth)',
          height: 'data(flowHeight)',
        },
      },
      {
        selector: 'edge',
        style: {
          width: 'data(resultWidth)',
          'line-color': '#71857e',
          'target-arrow-color': '#8ca098',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'control-point-step-size': 42,
          label: '',
          color: '#dbe4e0',
          'font-size': 10,
          'font-weight': 600,
          'text-background-color': '#111d1a',
          'text-background-opacity': 0.96,
          'text-background-padding': 4,
        },
      },
      {
        selector: 'edge.flow-mode',
        style: {
          width: 'data(flowWidth)',
          label: '',
          'line-color': '#b7e45f',
          'source-arrow-color': '#b7e45f',
          'target-arrow-color': '#b7e45f',
          'source-arrow-shape': 'triangle',
          'target-arrow-shape': 'none',
        },
      },
      {
        selector: 'edge.administrative',
        style: {
          'line-color': '#df654f',
          'target-arrow-color': '#df654f',
          'line-style': 'dashed',
        },
      },
      {
        selector: 'edge.tie',
        style: {
          'source-arrow-shape': 'triangle',
          'source-arrow-color': '#8ca098',
          'line-style': 'dotted',
        },
      },
      {
        selector: 'edge.flow-mode.zero-flow',
        style: {
          opacity: 0.14,
          label: '',
          'source-arrow-shape': 'none',
          'target-arrow-shape': 'none',
        },
      },
      {
        selector: 'edge.show-label',
        style: {
          label: 'data(resultLabel)',
        },
      },
      {
        selector: 'edge.flow-mode.show-label',
        style: {
          label: 'data(flowLabel)',
        },
      },
      {
        selector: '.faded',
        style: {
          opacity: 0.1,
          'text-opacity': 0.08,
        },
      },
      {
        selector: 'node.focused',
        style: {
          'border-width': 5,
          'border-color': '#f4f8f5',
        },
      },
      {
        selector: ':selected',
        style: {
          'border-color': '#b7e45f',
          'border-width': 4,
          'line-color': '#b7e45f',
          'target-arrow-color': '#b7e45f',
        },
      },
    ],
  });

  function runLayout() {
    const layout = graph.cycles.length
      ? {
        name: 'circle',
        avoidOverlap: true,
        spacingFactor: 1.08,
        startAngle: -Math.PI / 2,
        sweep: 2 * Math.PI,
        padding: 80,
        animate: false,
      }
      : {
        name: 'dagre',
        rankDir: 'LR',
        rankSep: 130,
        nodeSep: 55,
        edgeSep: 28,
        padding: 45,
        animate: false,
      };
    graphView
      .elements()
      .filter((element) => element.isNode() || element.data('competitive'))
      .layout(layout)
      .run();
  }

  renderTopology(graph);
  renderFlowRanking(graph);
  let currentMode = 'results';
  const caption = document.querySelector('#graph-caption');
  const topology = document.querySelector('#topology-flow');
  const flowRanking = document.querySelector('#flow-ranking');
  const resultKey = document.querySelector('#result-key');
  const flowKey = document.querySelector('#flow-key');
  const flowButton = document.querySelector('[data-graph-mode="flow"]');
  const labelToggle = document.querySelector('#graph-label-toggle');
  let showAllLabels = false;

  if (!graph.flow.available) {
    flowButton.disabled = true;
    flowButton.title = graph.flow.unavailableReason;
    flowButton.setAttribute('aria-disabled', 'true');
  }

  function clearFocus() {
    graphView.elements().removeClass('faded focused neighborhood-label');
    if (!showAllLabels) graphView.edges().removeClass('show-label');
  }

  function focusNode(node) {
    clearFocus();
    const neighborhood = node.closedNeighborhood();
    graphView.elements().addClass('faded');
    neighborhood.removeClass('faded');
    node.addClass('focused');
    node.connectedEdges().addClass('show-label neighborhood-label');
    caption.textContent = `${node.data('label')}: showing ${node.connectedEdges().length} connected results. Click the background to clear.`;
  }

  function setAllLabels(enabled) {
    showAllLabels = enabled;
    labelToggle.classList.toggle('active', enabled);
    labelToggle.setAttribute('aria-pressed', String(enabled));
    labelToggle.textContent = enabled ? 'Hide score labels' : 'Show all scores';
    graphView.edges().toggleClass('show-label', enabled);
  }

  function setMode(mode) {
    currentMode = mode;
    const isFlow = mode === 'flow';
    graphView.elements().toggleClass('flow-mode', isFlow);
    document.querySelectorAll('[data-graph-mode]').forEach((button) => {
      const active = button.dataset.graphMode === mode;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    topology.hidden = isFlow;
    flowRanking.hidden = !isFlow;
    resultKey.hidden = isFlow;
    flowKey.hidden = !isFlow;
    caption.textContent = isFlow
      ? 'Arrowheads point toward the winner receiving credit. Node size is retained résumé share.'
      : 'Hover a score for match details. Node size and fill represent opponent-adjusted strength.';
    runLayout();
  }

  graphView.on('mouseover', 'edge', (event) => {
    const edge = event.target;
    edge.addClass('show-label');
    caption.textContent = currentMode === 'flow'
      ? `${edge.data('flowCredit').toFixed(2)} credit flows back to the winner: ${edge.data('title')}`
      : `${edge.data('title')} · margin ${edge.data('scoreMargin')}`;
  });
  graphView.on('mouseout', 'edge', () => {
    if (!showAllLabels) {
      graphView.edges().not('.neighborhood-label').removeClass('show-label');
    }
    caption.textContent = currentMode === 'flow'
      ? 'Arrowheads point toward the winner receiving credit. Node size is retained résumé share.'
      : 'Hover a score for match details. Node size and fill represent opponent-adjusted strength.';
  });
  graphView.on('tap', 'node', (event) => focusNode(event.target));
  graphView.on('tap', (event) => {
    if (event.target === graphView) {
      clearFocus();
      caption.textContent = graph.cycles.length
        ? 'Cycle-safe circular layout. Click a team to reveal only its scores and opponents.'
        : 'Hover a result or click a team to inspect its neighborhood.';
    }
  });
  document.querySelectorAll('[data-graph-mode]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!button.disabled) setMode(button.dataset.graphMode);
    });
  });
  labelToggle.addEventListener('click', () => setAllLabels(!showAllLabels));
  setMode('results');
  caption.textContent = graph.cycles.length
    ? 'Cycle-safe circular layout. Click a team to reveal only its scores and opponents.'
    : 'Hover a result or click a team to inspect its neighborhood.';
  return graphView;
}