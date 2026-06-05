import axios from 'axios';

// Resolve base URL: check environment variable or fallback to Vite proxy prefix
const getBaseUrl = () => {
  let url = import.meta.env.VITE_API_BASE_URL;
  if (!url) {
    return '/api'; // fallback to vite proxy
  }
  return url.replace(/\/$/, ''); // strip trailing slash
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
  (response) => response,
  (error) => {
    let msg = 'An unexpected error occurred';
    if (error.response) {
      const detail = error.response.data?.detail;
      if (typeof detail === 'string') {
        msg = detail;
      } else if (detail?.message) {
        msg = detail.message;
      } else {
        msg = `Server returned error (${error.response.status})`;
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
