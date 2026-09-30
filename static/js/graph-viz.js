/**
 * D3.js Force-Directed Graph Visualization
 * 
 * Renders the eTIMS transaction knowledge graph with:
 *   - Force-directed layout
 *   - Curved edges for bidirectionality
 *   - Animated particles to represent real-life invoice flow
 *   - Node size mapped to financial risk & volume
 *   - Interactive hover tooltips
 *   - Zoom and pan
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
        this.animationFrame = null;
    }

    clear() {
        if (this.simulation) this.simulation.stop();
        if (this.animationFrame) cancelAnimationFrame(this.animationFrame);
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

        this.svg = d3.select(this.container)
            .append('svg')
            .attr('width', this.width)
            .attr('height', this.height);

        // Inject animation style for pulsing cycle paths
        const style = this.svg.append('style');
        style.text(`
            @keyframes pulse-stroke {
                0% { stroke-dashoffset: 20; opacity: 0.8; }
                50% { stroke-dashoffset: 0; opacity: 1; }
                100% { stroke-dashoffset: -20; opacity: 0.8; }
            }
            .cycle-pulsing {
                stroke: #ef476f !important;
                stroke-dasharray: 6 3 !important;
                animation: pulse-stroke 1.2s infinite linear;
            }
        `);

        const defs = this.svg.append('defs');

        // Arrow marker for valid edges
        defs.append('marker')
            .attr('id', 'arrow-valid')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 28)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L10,0L0,4')
            .attr('fill', 'rgba(76, 201, 240, 0.6)');

        // Arrow marker for flagged edges
        defs.append('marker')
            .attr('id', 'arrow-flagged')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 28)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L10,0L0,4')
            .attr('fill', '#ef476f');

        // Glow filter
        const filter = defs.append('filter')
            .attr('id', 'glow')
            .attr('x', '-50%').attr('y', '-50%')
            .attr('width', '200%').attr('height', '200%');
        filter.append('feGaussianBlur')
            .attr('stdDeviation', '4')
            .attr('result', 'blur');
        filter.append('feMerge')
            .selectAll('feMergeNode')
            .data(['blur', 'SourceGraphic'])
            .enter().append('feMergeNode')
            .attr('in', d => d);

        const zoom = d3.zoom()
            .scaleExtent([0.1, 8])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });

        this.svg.call(zoom);

        const g = this.svg.append('g');

        // Physics Simulation
        this.simulation = d3.forceSimulation(this.nodes)
            .force('link', d3.forceLink(this.edges)
                .id(d => d.id)
                .distance(d => d.status === 'FLAGGED' ? 120 : 200)
                .strength(0.6))
            .force('charge', d3.forceManyBody()
                .strength(d => d.flagged ? -800 : -400)
                .distanceMax(600))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(d => 40 + (d.transaction_count || 0)))
            .force('x', d3.forceX(this.width / 2).strength(0.05))
            .force('y', d3.forceY(this.height / 2).strength(0.05));

        // Draw edges as paths for curves
        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('path')
            .data(this.edges)
            .enter().append('path')
            .attr('fill', 'none')
            .attr('stroke', d => d.status === 'FLAGGED' ? 'rgba(239, 71, 111, 0.8)' : 'rgba(76, 201, 240, 0.3)')
            .attr('stroke-width', d => {
                const maxAmt = Math.max(...this.edges.map(e => e.amount || 1));
                return Math.max(1.5, (d.amount / maxAmt) * 8);
            })
            .attr('stroke-dasharray', d => d.status === 'FLAGGED' ? '6 4' : 'none')
            .attr('marker-end', d => d.status === 'FLAGGED' ? 'url(#arrow-flagged)' : 'url(#arrow-valid)')
            .attr('id', (d, i) => 'edgepath' + i)
            .classed('cycle-pulsing', d => d.status === 'FLAGGED');

        // Animated particles along edges representing invoices
        const particles = g.append('g')
            .attr('class', 'particles')
            .selectAll('circle')
            .data(this.edges)
            .enter().append('circle')
            .attr('r', 3)
            .attr('fill', d => d.status === 'FLAGGED' ? '#ef476f' : '#06d6a0')
            .attr('filter', 'url(#glow)');

        // Node definitions
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

        // Calculate node radius dynamically based on real-world volume
        const getRadius = d => {
            const base = 14;
            const extra = Math.min((d.transaction_count || 0) * 0.8, 16);
            return base + extra;
        };

        // Outer glow/ring
        node.append('circle')
            .attr('r', d => getRadius(d) + 4)
            .attr('fill', 'none')
            .attr('stroke', d => d.flagged ? 'rgba(239,71,111,0.3)' : 'rgba(6,214,160,0.2)')
            .attr('stroke-width', 2);

        // Main Node body
        node.append('circle')
            .attr('r', getRadius)
            .attr('fill', d => d.flagged ? '#ef476f' : '#111827')
            .attr('stroke', d => d.flagged ? '#fff' : '#06d6a0')
            .attr('stroke-width', d => d.flagged ? 2 : 3)
            .attr('filter', d => d.flagged ? 'url(#glow)' : 'none')
            .style('cursor', 'grab');

        // Central icon (Company/Building)
        node.append('text')
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'central')
            .attr('font-family', 'sans-serif')
            .attr('font-size', d => getRadius(d) * 0.9 + 'px')
            .attr('fill', d => d.flagged ? '#fff' : '#4cc9f0')
            .style('pointer-events', 'none')
            .text(d => d.flagged ? '⚠' : '🏢');

        // Node labels
        node.append('text')
            .attr('dy', d => getRadius(d) + 16)
            .attr('text-anchor', 'middle')
            .attr('font-size', '11px')
            .attr('font-weight', '700')
            .attr('fill', d => d.flagged ? '#ef476f' : 'var(--text-primary)')
            .attr('font-family', "'Inter', sans-serif")
            .style('text-shadow', '0px 2px 4px rgba(0,0,0,0.8)')
            .text(d => d.name ? (d.name.length > 20 ? d.name.slice(0, 18) + '…' : d.name) : d.id.slice(0, 8));

        // Secondary Node Labels (Risk / Compliance Ratio)
        node.append('text')
            .attr('dy', d => getRadius(d) + 30)
            .attr('text-anchor', 'middle')
            .attr('font-size', '9px')
            .attr('font-weight', '600')
            .attr('fill', d => d.flagged ? '#ef476f' : 'var(--text-muted)')
            .style('text-shadow', '0px 1px 2px rgba(0,0,0,0.8)')
            .text(d => d.flagged ? `Risk Score: ${(d.risk_score * 100).toFixed(0)}%` : `Invoices: ${d.transaction_count || 0}`);

        // Interaction events
        const self = this;
        node.on('mouseover', function(event, d) {
            self._showTooltip(event, d);
            d3.select(this).select('circle:nth-child(2)')
                .transition().duration(200)
                .attr('stroke-width', 5)
                .attr('r', getRadius(d) + 2);
        })
        .on('mouseout', function(event, d) {
            self._hideTooltip();
            d3.select(this).select('circle:nth-child(2)')
                .transition().duration(200)
                .attr('stroke-width', d.flagged ? 2 : 3)
                .attr('r', getRadius(d));
        });

        link.on('mouseover', function(event, d) {
            self._showEdgeTooltip(event, d);
            d3.select(this)
                .transition().duration(200)
                .attr('stroke-width', parseFloat(d3.select(this).attr('stroke-width')) + 3)
                .attr('stroke', d.status === 'FLAGGED' ? '#ff003c' : '#00f0ff');
        })
        .on('mouseout', function(event, d) {
            self._hideTooltip();
            const maxAmt = Math.max(...self.edges.map(e => e.amount || 1));
            d3.select(this)
                .transition().duration(200)
                .attr('stroke-width', Math.max(1.5, (d.amount / maxAmt) * 8))
                .attr('stroke', d.status === 'FLAGGED' ? 'rgba(239, 71, 111, 0.8)' : 'rgba(76, 201, 240, 0.3)');
        });

        // Animation loop for particles
        const animateParticles = () => {
            const time = Date.now();
            particles.attr('transform', function(d, i) {
                const pathNode = document.getElementById('edgepath' + i);
                if (!pathNode) return 'translate(0,0)';
                const length = pathNode.getTotalLength();
                if (length === 0) return 'translate(0,0)';
                // Speed based on amount (faster for larger amounts)
                const maxAmt = Math.max(...self.edges.map(e => e.amount || 1));
                const speed = 0.0003 + ((d.amount / maxAmt) * 0.0006);
                const p = (time * speed) % 1;
                const point = pathNode.getPointAtLength(p * length);
                return `translate(${point.x},${point.y})`;
            });
            self.animationFrame = requestAnimationFrame(animateParticles);
        };
        animateParticles();

        // Simulation tick logic with curved paths
        this.simulation.on('tick', () => {
            link.attr('d', d => {
                const dx = d.target.x - d.source.x,
                      dy = d.target.y - d.source.y,
                      dr = Math.sqrt(dx * dx + dy * dy) * 1.2; // 1.2 adds a subtle professional curve
                
                // If it's a self loop
                if (d.target === d.source) {
                    const x = d.source.x;
                    const y = d.source.y;
                    return `M${x},${y} A 30,30 0 1,1 ${x+1},${y+1}`;
                }
                
                return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
            });

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Initial zoom to fit
        setTimeout(() => {
            this.svg.transition().duration(750).call(
                zoom.transform,
                d3.zoomIdentity.translate(0, 0).scale(0.85)
            );
        }, 1200);
    }

    _showTooltip(event, d) {
        const vatStr = d.vat_claimed ? `KSh ${(d.vat_claimed / 1e6).toFixed(2)}M` : 'N/A';
        this.tooltip.innerHTML = `
            <div class="tooltip-title">${d.name || d.id}</div>
            <div class="tooltip-row"><span class="label">PIN</span><span class="value">${d.id}</span></div>
            <div class="tooltip-row"><span class="label">Sector</span><span class="value">${d.sector || 'Unknown'}</span></div>
            <div class="tooltip-row"><span class="label">Risk Profile</span><span class="value" style="color:${d.risk_score > 0.5 ? '#ef476f' : '#06d6a0'}">${(d.risk_score * 100).toFixed(1)}%</span></div>
            <div class="tooltip-row"><span class="label">Total Invoices</span><span class="value">${d.transaction_count || 0}</span></div>
            <div class="tooltip-row"><span class="label">VAT Claimed</span><span class="value">${vatStr}</span></div>
            <div class="tooltip-row"><span class="label">Status</span><span class="value" style="color:${d.flagged ? '#ef476f' : '#06d6a0'}">${d.flagged ? '⚠ IDENTIFIED IN RING' : '✓ CLEAN'}</span></div>
        `;
        this._positionTooltip(event);
    }

    _showEdgeTooltip(event, d) {
        this.tooltip.innerHTML = `
            <div class="tooltip-title">Invoice Flow Data</div>
            <div class="tooltip-row"><span class="label">Supplier (Issuer)</span><span class="value">${typeof d.source === 'object' ? d.source.id : d.source}</span></div>
            <div class="tooltip-row"><span class="label">Buyer (Claimant)</span><span class="value">${typeof d.target === 'object' ? d.target.id : d.target}</span></div>
            <div class="tooltip-row"><span class="label">Total Value</span><span class="value">KSh ${(d.amount / 1e6).toFixed(2)}M</span></div>
            <div class="tooltip-row"><span class="label">VAT Amount</span><span class="value">KSh ${(d.vat / 1e6).toFixed(2)}M</span></div>
            <div class="tooltip-row"><span class="label">Invoice Count</span><span class="value">${d.count || 1}</span></div>
            <div class="tooltip-row"><span class="label">Transaction Status</span><span class="value" style="color:${d.status === 'FLAGGED' ? '#ef476f' : '#06d6a0'}">${d.status === 'FLAGGED' ? '⚠ SUSPICIOUS' : '✓ VERIFIED'}</span></div>
        `;
        this._positionTooltip(event);
    }

    _positionTooltip(event) {
        this.tooltip.style.display = 'block';
        
        const containerRect = this.container.getBoundingClientRect();
        let left = event.clientX - containerRect.left + 20;
        let top = event.clientY - containerRect.top - 20;

        const tooltipRect = this.tooltip.getBoundingClientRect();
        
        // Prevent tooltip from overflowing the right edge
        if (left + tooltipRect.width > containerRect.width) {
            left = event.clientX - containerRect.left - tooltipRect.width - 20;
        }
        
        // Prevent tooltip from overflowing bottom edge
        if (top + tooltipRect.height > containerRect.height) {
            top = containerRect.height - tooltipRect.height - 10;
        }
        
        // Prevent tooltip from overflowing top edge
        if (top < 0) top = 10;

        this.tooltip.style.left = left + 'px';
        this.tooltip.style.top = top + 'px';
    }

    _hideTooltip() {
        this.tooltip.style.display = 'none';
    }

    _dragStart(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
        d3.select(this.container).style('cursor', 'grabbing');
    }

    _drag(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    _dragEnd(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
        d3.select(this.container).style('cursor', 'default');
    }

    resetView() {
        if (this.svg) {
            this.svg.transition().duration(750).call(
                d3.zoom().transform,
                d3.zoomIdentity
            );
        }
    }
}
