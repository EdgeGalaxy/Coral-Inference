

// 获取API基础URL
export const getApiBaseUrl = () => {
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:9001';
      }
    }
    return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9001';
  };