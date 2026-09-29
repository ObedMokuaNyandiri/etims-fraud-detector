/**
 * Dashboard — Chart.js visualizations and stat card management.
 */

class Dashboard {
    constructor() {
        this.riskChart = null;
        this.ringChart = null;
    }

    async loadStats() {
        try {
            const stats = await API.getDashboardStats();
            this._updateStatCards(stats);
        } catch (err) {
            console.warn('Could not load stats:', err.message);
        }
    }

    _updateStatCards(stats) {
        const animate = (el, target) => {
            if (!el) return;
            const isAmount = target > 10000;
            const formatted = isAmount
                ? `${(target / 1e6).toFixed(1)}M`
                : target.toLocaleString();
            
            // Simple counter animation
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
            setTimeout(() => {
                el.textContent = formatted;
                el.style.transition = 'all 0.4s cubic-bezier(0.22, 1, 0.36, 1)';
                el.style.opacity = '1';
                el.style.transform = 'translateY(0)';
            }, 100);
        };

        animate(document.getElementById('stat-transactions'), stats.total_transactions);
        animate(document.getElementById('stat-companies'), stats.total_companies);
        animate(document.getElementById('stat-rings'), stats.total_fraud_rings);
        animate(document.getElementById('stat-fraud-amount'), stats.total_fraud_amount);
        animate(document.getElementById('stat-vat'), stats.total_vat_at_risk);
        animate(document.getElementById('stat-flagged'), stats.flagged_companies);

        // Update rings badge
        const badge = document.getElementById('rings-badge');
        if (stats.total_fraud_rings > 0) {
            badge.textContent = stats.total_fraud_rings;
            badge.style.display = 'inline';
        } else {
            badge.style.display = 'none';
        }
    }

    async loadCharts() {
        try {
            const [topRisks, rings] = await Promise.all([
                API.getTopRisks(8),
                API.getFraudRings(),
            ]);
            this._renderRiskChart(topRisks);
            this._renderRingChart(rings);
        } catch (err) {
            console.warn('Could not load charts:', err.message);
        }
    }

    _renderRiskChart(companies) {
        const ctx = document.getElementById('risk-chart');
        if (!ctx) return;

        if (this.riskChart) this.riskChart.destroy();

        const labels = companies.map(c => c.name.length > 15 ? c.name.slice(0, 13) + '…' : c.name);
        const data = companies.map(c => (c.risk_score * 100).toFixed(1));
        const colors = companies.map(c =>
            c.risk_score > 0.6 ? '#ef476f' :
            c.risk_score > 0.3 ? '#ffd166' : '#06d6a0'
        );

        this.riskChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Risk Score (%)',
                    data,
                    backgroundColor: colors.map(c => c + '40'),
                    borderColor: colors,
                    borderWidth: 1.5,
                    borderRadius: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        borderColor: 'rgba(76, 201, 240, 0.3)',
                        borderWidth: 1,
                        titleFont: { family: "'Inter', sans-serif", weight: '600' },
                        bodyFont: { family: "'JetBrains Mono', monospace" },
                        callbacks: {
                            label: ctx => `Risk: ${ctx.parsed.x}%`,
                        },
                    },
                },
                scales: {
                    x: {
                        max: 100,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#64748b', font: { size: 11 } },
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { size: 11, family: "'Inter', sans-serif" } },
                    },
                },
            },
        });
    }

    _renderRingChart(rings) {
        const ctx = document.getElementById('ring-chart');
        if (!ctx) return;

        if (this.ringChart) this.ringChart.destroy();

        if (!rings || rings.length === 0) {
            this.ringChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['No Data'],
                    datasets: [{ data: [1], backgroundColor: ['rgba(100,116,139,0.2)'], borderWidth: 0 }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                },
            });
            return;
        }

        const palette = ['#ef476f', '#ffd166', '#06d6a0', '#4cc9f0', '#7209b7', '#f72585', '#ff6b35'];

        this.ringChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: rings.map((r, i) => `Ring #${r.id} (${r.cycle_length}-node)`),
                datasets: [{
                    data: rings.map(r => r.total_amount),
                    backgroundColor: rings.map((_, i) => palette[i % palette.length] + '60'),
                    borderColor: rings.map((_, i) => palette[i % palette.length]),
                    borderWidth: 2,
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#94a3b8',
                            padding: 12,
                            font: { size: 11, family: "'Inter', sans-serif" },
                            usePointStyle: true,
                            pointStyleWidth: 8,
                        },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        borderColor: 'rgba(76, 201, 240, 0.3)',
                        borderWidth: 1,
                        callbacks: {
                            label: ctx => `KSh ${(ctx.parsed / 1e6).toFixed(1)}M`,
                        },
                    },
                },
            },
        });
    }
}
