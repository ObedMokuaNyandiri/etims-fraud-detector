/**
 * App — Main SPA controller for the eTIMS Knowledge Graph Engine.
 * 
 * Handles:
 *   - Page routing (sidebar navigation)
 *   - Mock data generation
 *   - Analysis execution
 *   - CSV upload with drag-and-drop
 *   - Fraud ring list + detail modal
 *   - Toast notifications
 */

(function () {
    'use strict';

    // ── Instances ───────────────────────────────────────────────────────────
    const dashboard = new Dashboard();
    const graphViz = new GraphViz('graph-canvas');

    // ── Routing ─────────────────────────────────────────────────────────────
    const navLinks = document.querySelectorAll('.nav-link');
    const pages = document.querySelectorAll('.page');

    function navigateTo(pageName) {
        navLinks.forEach(l => l.classList.toggle('active', l.dataset.page === pageName));
        pages.forEach(p => p.classList.toggle('active', p.id === `page-${pageName}`));

        // Lazy-load page data
        if (pageName === 'dashboard') {
            dashboard.loadStats();
            dashboard.loadCharts();
        } else if (pageName === 'graph') {
            loadGraph();
        } else if (pageName === 'rings') {
            loadRings();
        }
    }

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navigateTo(link.dataset.page);
        });
    });

    // ── Toast Notifications ─────────────────────────────────────────────────
    function toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const icons = { success: '✓', error: '✗', info: 'ℹ' };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ'}</span><span>${message}</span>`;
        container.appendChild(el);
        setTimeout(() => {
            el.style.animation = 'slideOut 0.3s forwards';
            setTimeout(() => el.remove(), 300);
        }, 4000);
    }

    // ── Loading Overlay ─────────────────────────────────────────────────────
    function showLoading(text = 'Processing...') {
        document.getElementById('loading-text').textContent = text;
        document.getElementById('loading-overlay').style.display = 'flex';
    }

    function hideLoading() {
        document.getElementById('loading-overlay').style.display = 'none';
    }

    // ── Run Detection ───────────────────────────────────────────────────────
    document.getElementById('btn-run-analysis').addEventListener('click', async () => {
        try {
            showLoading('Running Johnson\'s cycle detection algorithm on transaction graph...');
            const result = await API.runDetection({ max_cycle_length: 8, min_amount_threshold: 0 });
            hideLoading();

            if (result.rings_detected > 0) {
                toast(`🔴 Detected ${result.rings_detected} fraud rings worth KSh ${(result.total_fraud_amount / 1e6).toFixed(1)}M in ${result.duration_seconds.toFixed(2)}s`, 'error');
            } else {
                toast(`✓ Analysis complete. No fraud rings detected. ${result.transactions_analyzed} edges analyzed in ${result.duration_seconds.toFixed(2)}s`, 'success');
            }

            dashboard.loadStats();
            dashboard.loadCharts();
            loadRingFilter();
        } catch (err) {
            hideLoading();
            toast(err.message, 'error');
        }
    });

    // ── Graph Explorer ──────────────────────────────────────────────────────
    async function loadGraph(ringId = null) {
        try {
            const data = await API.getGraphData(ringId);
            await graphViz.render(data);
        } catch (err) {
            console.warn('Graph load error:', err.message);
        }
    }

    document.getElementById('btn-reset-graph').addEventListener('click', () => {
        graphViz.resetView();
    });

    // Ring filter dropdown
    async function loadRingFilter() {
        const select = document.getElementById('graph-ring-filter');
        try {
            const rings = await API.getFraudRings();
            // Clear existing options except the first
            while (select.options.length > 1) select.remove(1);
            rings.forEach(r => {
                const opt = document.createElement('option');
                opt.value = r.id;
                opt.textContent = `Ring #${r.id} — ${r.cycle_length}-node (KSh ${(r.total_amount / 1e6).toFixed(1)}M)`;
                select.appendChild(opt);
            });
        } catch (err) {
            console.warn('Could not load ring filter:', err.message);
        }
    }

    document.getElementById('graph-ring-filter').addEventListener('change', (e) => {
        const val = e.target.value;
        loadGraph(val ? parseInt(val) : null);
    });

    // ── Fraud Rings List ────────────────────────────────────────────────────
    async function loadRings() {
        const container = document.getElementById('rings-container');
        try {
            const rings = await API.getFraudRings();
            if (!rings || rings.length === 0) {
                container.innerHTML = document.getElementById('rings-empty').outerHTML;
                return;
            }

            container.innerHTML = rings.map(ring => {
                const members = JSON.parse(ring.member_pins);
                const confClass = ring.confidence_score > 0.7 ? 'high' : ring.confidence_score > 0.4 ? 'medium' : 'low';
                const confLabel = ring.confidence_score > 0.7 ? 'HIGH' : ring.confidence_score > 0.4 ? 'MEDIUM' : 'LOW';

                return `
                    <div class="ring-card" data-ring-id="${ring.id}">
                        <div class="ring-card-header">
                            <span class="ring-id">RING #${ring.id}</span>
                            <span class="ring-confidence ${confClass}">${confLabel} (${(ring.confidence_score * 100).toFixed(0)}%)</span>
                        </div>
                        <div class="ring-stats">
                            <div class="ring-stat">
                                <span class="ring-stat-value">${ring.cycle_length}</span>
                                <span class="ring-stat-label">Entities</span>
                            </div>
                            <div class="ring-stat">
                                <span class="ring-stat-value">KSh ${(ring.total_amount / 1e6).toFixed(1)}M</span>
                                <span class="ring-stat-label">Total Amount</span>
                            </div>
                            <div class="ring-stat">
                                <span class="ring-stat-value">KSh ${(ring.total_vat / 1e6).toFixed(1)}M</span>
                                <span class="ring-stat-label">VAT at Risk</span>
                            </div>
                            <div class="ring-stat">
                                <span class="ring-stat-value">${ring.status}</span>
                                <span class="ring-stat-label">Status</span>
                            </div>
                        </div>
                        <div class="ring-members">
                            ${members.map(p => `<span class="ring-member-pill">${p}</span>`).join('')}
                        </div>
                    </div>
                `;
            }).join('');

            // Click handlers for ring detail modal
            container.querySelectorAll('.ring-card').forEach(card => {
                card.addEventListener('click', () => {
                    const ringId = parseInt(card.dataset.ringId);
                    showRingModal(ringId);
                });
            });

        } catch (err) {
            console.warn('Could not load rings:', err.message);
        }
    }

    // ── Ring Detail Modal ───────────────────────────────────────────────────
    async function showRingModal(ringId) {
        try {
            const ring = await API.getFraudRing(ringId);
            const members = JSON.parse(ring.member_pins);

            const flowHTML = members.map((pin, i) => {
                const arrow = i < members.length - 1
                    ? '<span class="modal-ring-arrow">→</span>'
                    : '<span class="modal-ring-arrow">↩</span>';
                return `<span class="modal-ring-node">${pin}</span>${arrow}`;
            }).join('');

            document.getElementById('modal-title').textContent = `Fraud Ring #${ring.id}`;
            document.getElementById('modal-body').innerHTML = `
                <div class="modal-ring-flow">${flowHTML}</div>
                <div class="modal-detail-grid">
                    <div class="modal-detail">
                        <div class="modal-detail-label">Cycle Length</div>
                        <div class="modal-detail-value">${ring.cycle_length} entities</div>
                    </div>
                    <div class="modal-detail">
                        <div class="modal-detail-label">Total Invoice Amount</div>
                        <div class="modal-detail-value">KSh ${(ring.total_amount / 1e6).toFixed(2)}M</div>
                    </div>
                    <div class="modal-detail">
                        <div class="modal-detail-label">VAT at Risk</div>
                        <div class="modal-detail-value" style="color:#ef476f">KSh ${(ring.total_vat / 1e6).toFixed(2)}M</div>
                    </div>
                    <div class="modal-detail">
                        <div class="modal-detail-label">Confidence Score</div>
                        <div class="modal-detail-value">${(ring.confidence_score * 100).toFixed(1)}%</div>
                    </div>
                    <div class="modal-detail">
                        <div class="modal-detail-label">Ring Hash</div>
                        <div class="modal-detail-value" style="font-size:0.75rem">${ring.ring_hash}</div>
                    </div>
                    <div class="modal-detail">
                        <div class="modal-detail-label">Status</div>
                        <div class="modal-detail-value">${ring.status}</div>
                    </div>
                </div>
                <div style="margin-top:1.5rem;text-align:center">
                    <button class="btn btn-primary" onclick="document.getElementById('graph-ring-filter').value='${ring.id}';document.getElementById('nav-graph').click();document.getElementById('ring-modal').style.display='none';document.getElementById('graph-ring-filter').dispatchEvent(new Event('change'));">
                        View in Graph Explorer →
                    </button>
                </div>
            `;

            document.getElementById('ring-modal').style.display = 'flex';
        } catch (err) {
            toast('Failed to load ring details', 'error');
        }
    }

    // Modal close
    document.getElementById('modal-close').addEventListener('click', () => {
        document.getElementById('ring-modal').style.display = 'none';
    });
    document.getElementById('ring-modal').addEventListener('click', (e) => {
        if (e.target.id === 'ring-modal') {
            document.getElementById('ring-modal').style.display = 'none';
        }
    });

    // ── CSV Upload ──────────────────────────────────────────────────────────
    const uploadZone = document.getElementById('upload-zone');
    const csvInput = document.getElementById('csv-input');
    const uploadResult = document.getElementById('upload-result');

    uploadZone.addEventListener('click', () => csvInput.click());

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) handleUpload(file);
    });

    csvInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleUpload(file);
    });

    async function handleUpload(file) {
        try {
            showLoading(`Parsing and validating ${file.name}...`);
            const result = await API.uploadCSV(file);
            hideLoading();

            uploadResult.style.display = 'block';
            uploadResult.className = 'upload-result success';
            uploadResult.innerHTML = `
                <strong>✓ Upload Successful</strong><br>
                ${result.transactions_imported} transactions imported<br>
                ${result.companies_created} new companies created<br>
                ${result.duplicates_skipped} duplicates skipped
                ${result.errors.length > 0 ? `<br><br><strong>Warnings:</strong><br>${result.errors.slice(0, 5).join('<br>')}` : ''}
            `;

            toast(`Imported ${result.transactions_imported} transactions from ${file.name}`, 'success');
            dashboard.loadStats();

            // Automatically trigger analysis if any transactions exist in the graph
            if (result.transactions_imported > 0 || result.duplicates_skipped > 0) {
                document.getElementById('btn-run-analysis').click();
            }
        } catch (err) {
            hideLoading();
            uploadResult.style.display = 'block';
            uploadResult.className = 'upload-result error';
            uploadResult.innerHTML = `<strong>✗ Upload Failed</strong><br>${err.message}`;
            toast('Upload failed: ' + err.message, 'error');
        }
    }

    // ── Initial Load ────────────────────────────────────────────────────────
    navigateTo('dashboard');
    loadRingFilter();

})();
