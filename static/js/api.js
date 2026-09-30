/**
 * API Client — Centralized HTTP client for the eTIMS Knowledge Graph Engine.
 */

const API = {
    BASE: '',

    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body && method !== 'GET') {
            opts.body = JSON.stringify(body);
        }
        const res = await fetch(`${this.BASE}${path}`, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || JSON.stringify(err));
        }
        return res.json();
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },

    async uploadCSV(file) {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${this.BASE}/api/transactions/upload`, {
            method: 'POST',
            body: form,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || JSON.stringify(err));
        }
        return res.json();
    },

    // Convenience methods
    getDashboardStats()  { return this.get('/api/dashboard/stats'); },
    getTopRisks(limit=10){ return this.get(`/api/dashboard/top-risks?limit=${limit}`); },
    getTimeline()        { return this.get('/api/dashboard/timeline'); },
    getGraphData(ringId) { return this.get(`/api/analysis/graph${ringId ? `?ring_id=${ringId}` : ''}`); },
    getFraudRings()      { return this.get('/api/analysis/rings'); },
    getFraudRing(id)     { return this.get(`/api/analysis/rings/${id}`); },
    runDetection(params) { return this.post('/api/analysis/detect', params || {}); },
};
