/**
 * D3.js Force-Directed Graph Visualization
 * 
 * Renders the eTIMS transaction knowledge graph with:
 *   - Force-directed layout
 *   - Color-coded nodes (clean vs flagged)
 *   - Directional arrows on edges
 *   - Interactive hover tooltips
 *   - Zoom and pan
 *   - Ring highlighting
 */

class GraphViz {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.edges = [];
        this.tooltip = document.getElementById('graph-tooltip');
        this.width = 0;
        this.height = 0;
    }

    clear() {
        if (this.simulation) this.simulation.stop();
        if (this.container) this.container.innerHTML = '';
    }

    async render(graphData) {
        this.clear();

        if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
            this.container.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:0.9rem;">
                    <div style="text-align:center">
                        <p style="font-size:2rem;margin-bottom:0.5rem;">📊</p>
                        <p>No graph data available.<br>Upload transactions and run detection first.</p>
                    </div>
                </div>`;
            return;
        }

        this.nodes = graphData.nodes.map(d => ({ ...d }));
        this.edges = graphData.edges.map(d => ({ ...d }));

        const rect = this.container.getBoundingClientRect();
        this.width = rect.width;
        this.height = rect.height;

        // Create SVG
        this.svg = d3.select(this.container)
            .append('svg')
            .attr('width', this.width)
            .attr('height', this.height);

        // Defs for arrowheads and gradients
        const defs = this.svg.append('defs');

        // Arrow marker for valid edges
        defs.append('marker')
            .attr('id', 'arrow-valid')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 22)
            .attr('refY', 0)
            .attr('markerWidth', 8)
            .attr('markerHeight', 8)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L10,0L0,4')
            .attr('fill', 'rgba(76, 201, 240, 0.4)');

        // Arrow marker for flagged edges
        defs.append('marker')
            .attr('id', 'arrow-flagged')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 22)
            .attr('refY', 0)
            .attr('markerWidth', 8)
            .attr('markerHeight', 8)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L10,0L0,4')
            .attr('fill', '#ef476f');

        // Node glow filter
        const filter = defs.append('filter')
            .attr('id', 'glow')
            .attr('x', '-50%').attr('y', '-50%')
            .attr('width', '200%').attr('height', '200%');
        filter.append('feGaussianBlur')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');
        filter.append('feMerge')
            .selectAll('feMergeNode')
            .data(['blur', 'SourceGraphic'])
            .enter().append('feMergeNode')
            .attr('in', d => d);

        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.2, 5])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });

        this.svg.call(zoom);

        // Main group for zoom transform
        const g = this.svg.append('g');

        // Force simulation
        this.simulation = d3.forceSimulation(this.nodes)
            .force('link', d3.forceLink(this.edges)
                .id(d => d.id)
                .distance(120)
                .strength(0.5))
            .force('charge', d3.forceManyBody()
                .strength(-300)
                .distanceMax(400))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(30))
            .force('x', d3.forceX(this.width / 2).strength(0.03))
            .force('y', d3.forceY(this.height / 2).strength(0.03));

        // Draw edges
        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(this.edges)
            .enter().append('line')
            .attr('stroke', d => d.status === 'FLAGGED' ? '#ef476f' : 'rgba(76, 201, 240, 0.25)')
            .attr('stroke-width', d => {
                const maxAmt = Math.max(...this.edges.map(e => e.amount || 1));
                return Math.max(1.5, (d.amount / maxAmt) * 5);
            })
            .attr('stroke-dasharray', d => d.status === 'FLAGGED' ? '6 3' : 'none')
            .attr('marker-end', d => d.status === 'FLAGGED' ? 'url(#arrow-flagged)' : 'url(#arrow-valid)');

        // Draw edge amount labels
        const edgeLabels = g.append('g')
            .attr('class', 'edge-labels')
            .selectAll('text')
            .data(this.edges)
            .enter().append('text')
            .attr('font-size', '9px')
            .attr('font-family', "'JetBrains Mono', monospace")
            .attr('fill', d => d.status === 'FLAGGED' ? '#ef476f' : 'rgba(76, 201, 240, 0.5)')
            .attr('text-anchor', 'middle')
            .text(d => d.amount ? `KSh ${(d.amount / 1e6).toFixed(1)}M` : '');

        // Draw nodes
        const node = g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .enter().append('g')
            .call(d3.drag()
                .on('start', (event, d) => this._dragStart(event, d))
                .on('drag', (event, d) => this._drag(event, d))
                .on('end', (event, d) => this._dragEnd(event, d))
            );

        // Node circles
        node.append('circle')
            .attr('r', d => {
                const base = 12;
                const extra = Math.min((d.transaction_count || 0) * 0.5, 8);
                return base + extra;
            })
            .attr('fill', d => d.flagged ? '#ef476f' : '#06d6a0')
            .attr('stroke', d => d.flagged ? 'rgba(239,71,111,0.4)' : 'rgba(6,214,160,0.3)')
            .attr('stroke-width', 3)
            .attr('filter', d => d.flagged ? 'url(#glow)' : 'none')
            .style('cursor', 'pointer');

        // Node labels
        node.append('text')
            .attr('dy', d => {
                const base = 12;
                const extra = Math.min((d.transaction_count || 0) * 0.5, 8);
                return base + extra + 14;
            })
            .attr('text-anchor', 'middle')
            .attr('font-size', '10px')
            .attr('font-weight', '600')
            .attr('fill', 'var(--text-secondary)')
            .attr('font-family', "'Inter', sans-serif")
            .text(d => d.name ? (d.name.length > 18 ? d.name.slice(0, 16) + '…' : d.name) : d.id.slice(0, 8));

        // Hover events
        const self = this;
        node.on('mouseover', function(event, d) {
            self._showTooltip(event, d);
            d3.select(this).select('circle')
                .transition().duration(200)
                .attr('stroke-width', 5);
        })
        .on('mouseout', function() {
            self._hideTooltip();
            d3.select(this).select('circle')
                .transition().duration(200)
                .attr('stroke-width', 3);
        });

        // Edge hover for amount details
        link.on('mouseover', function(event, d) {
            self._showEdgeTooltip(event, d);
            d3.select(this)
                .transition().duration(200)
                .attr('stroke-width', parseFloat(d3.select(this).attr('stroke-width')) + 2);
        })
        .on('mouseout', function(event, d) {
            self._hideTooltip();
            const maxAmt = Math.max(...self.edges.map(e => e.amount || 1));
            d3.select(this)
                .transition().duration(200)
                .attr('stroke-width', Math.max(1.5, (d.amount / maxAmt) * 5));
        });

        // Simulation tick
        this.simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            edgeLabels
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2 - 6);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Initial zoom to fit
        setTimeout(() => {
            this.svg.transition().duration(500).call(
                zoom.transform,
                d3.zoomIdentity.translate(0, 0).scale(0.85)
            );
        }, 1000);
    }

    _showTooltip(event, d) {
        const vatStr = d.vat_claimed ? `KSh ${(d.vat_claimed / 1e6).toFixed(2)}M` : 'N/A';
        this.tooltip.innerHTML = `
            <div class="tooltip-title">${d.name || d.id}</div>
            <div class="tooltip-row"><span class="label">PIN</span><span class="value">${d.id}</span></div>
            <div class="tooltip-row"><span class="label">Sector</span><span class="value">${d.sector || 'Unknown'}</span></div>
            <div class="tooltip-row"><span class="label">Risk Score</span><span class="value" style="color:${d.risk_score > 0.5 ? '#ef476f' : '#06d6a0'}">${(d.risk_score * 100).toFixed(1)}%</span></div>
            <div class="tooltip-row"><span class="label">Transactions</span><span class="value">${d.transaction_count || 0}</span></div>
            <div class="tooltip-row"><span class="label">VAT Claimed</span><span class="value">${vatStr}</span></div>
            <div class="tooltip-row"><span class="label">Status</span><span class="value" style="color:${d.flagged ? '#ef476f' : '#06d6a0'}">${d.flagged ? '⚠ FLAGGED' : '✓ CLEAN'}</span></div>
        `;
        this.tooltip.style.display = 'block';
        this.tooltip.style.left = (event.pageX - this.container.getBoundingClientRect().left + 15) + 'px';
        this.tooltip.style.top = (event.pageY - this.container.getBoundingClientRect().top - 10) + 'px';
    }

    _showEdgeTooltip(event, d) {
        this.tooltip.innerHTML = `
            <div class="tooltip-title">Invoice Flow</div>
            <div class="tooltip-row"><span class="label">From</span><span class="value">${typeof d.source === 'object' ? d.source.id : d.source}</span></div>
            <div class="tooltip-row"><span class="label">To</span><span class="value">${typeof d.target === 'object' ? d.target.id : d.target}</span></div>
            <div class="tooltip-row"><span class="label">Amount</span><span class="value">KSh ${(d.amount / 1e6).toFixed(2)}M</span></div>
            <div class="tooltip-row"><span class="label">VAT</span><span class="value">KSh ${(d.vat / 1e6).toFixed(2)}M</span></div>
            <div class="tooltip-row"><span class="label">Status</span><span class="value" style="color:${d.status === 'FLAGGED' ? '#ef476f' : '#06d6a0'}">${d.status}</span></div>
        `;
        this.tooltip.style.display = 'block';
        this.tooltip.style.left = (event.pageX - this.container.getBoundingClientRect().left + 15) + 'px';
        this.tooltip.style.top = (event.pageY - this.container.getBoundingClientRect().top - 10) + 'px';
    }

    _hideTooltip() {
        this.tooltip.style.display = 'none';
    }

    _dragStart(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    _drag(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    _dragEnd(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    resetView() {
        if (this.svg) {
            this.svg.transition().duration(500).call(
                d3.zoom().transform,
                d3.zoomIdentity
            );
        }
    }
}
