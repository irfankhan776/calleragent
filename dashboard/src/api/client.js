import axios from 'axios';

const PROD_API_ORIGIN = 'https://calleragent-production-cebe.up.railway.app';

const isHtmlDocument = (value) => typeof value === 'string' && /<!doctype html>|<html[\s>]/i.test(value);

// Resolve base URL: prefer explicit environment configuration, use a safe production fallback on Railway, and keep the local proxy for development.
const getBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envUrl) {
    return envUrl.replace(/\/$/, '');
  }

  if (typeof window !== 'undefined' && window.location.hostname.endsWith('railway.app')) {
    return PROD_API_ORIGIN;
  }

  return '/api';
};

const client = axios.create({
  baseURL: getBaseUrl(),
  timeout: 30000,
});

// Toast notification helper using CustomEvents
export const showToast = (message, type = 'info') => {
  const event = new CustomEvent('app-toast', {
    detail: { message, type, id: Date.now() }
  });
  window.dispatchEvent(event);
};

// Response interceptor for error handling
client.interceptors.response.use(
  (response) => {
    if (isHtmlDocument(response.data)) {
      const requestUrl = response?.request?.responseURL || response?.config?.url || 'unknown URL';
      const error = new Error(`API misconfiguration: received HTML instead of JSON from ${requestUrl}.`);
      error.response = response;
      throw error;
    }
    return response;
  },
  (error) => {
    let msg = 'An unexpected error occurred';
    if (error.response) {
      if (isHtmlDocument(error.response.data)) {
        const requestUrl = error.response?.request?.responseURL || error.response?.config?.url || 'unknown URL';
        msg = `Dashboard API is misconfigured: ${requestUrl} returned HTML instead of JSON.`;
      } else {
        const detail = error.response.data?.detail;
        if (typeof detail === 'string') {
          msg = detail;
        } else if (detail?.message) {
          msg = detail.message;
        } else {
          msg = `Server returned error (${error.response.status})`;
        }
      }
    } else if (error.request) {
      msg = 'No response received from server. Check your backend status.';
    } else {
      msg = error.message;
    }
    showToast(msg, 'error');
    return Promise.reject(error);
  }
);

export const api = {
  getCalls: async (params = {}) => {
    // Convert date filter to yyyy-mm-dd format if necessary
    const formattedParams = { ...params };
    const response = await client.get('/calls', { params: formattedParams });
    return response.data;
  },
  
  getCall: async (id) => {
    const response = await client.get(`/calls/${id}`);
    return response.data;
  },
  
  getStats: async () => {
    const response = await client.get('/stats');
    return response.data;
  },
  
  deleteCall: async (id) => {
    const response = await client.get(`/calls/${id}`).catch(() => null);
    const bizName = response?.data?.business_name || 'Call';
    
    await client.delete(`/calls/${id}`);
    showToast(`Successfully deleted ${bizName} call record`, 'success');
    return id;
  },
  
  postCSV: async (file, limit = null, dryRun = false) => {
    const formData = new FormData();
    formData.append('file', file);

    const params = {};
    if (limit !== null) params.limit = limit;
    if (dryRun) params.dry_run = true;

    const response = await client.post('/calls/upload', formData, {
      params,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    showToast('CSV uploaded and auto-dialer started!', 'success');
    return response.data;
  },

  getJobStatus: async (jobId) => {
    const response = await client.get(`/jobs/${jobId}/status`);
    return response.data;
  }
};

export default api;
