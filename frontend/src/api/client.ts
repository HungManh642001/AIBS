import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000/api/v1" });

// Backend trả lỗi nghiệp vụ kèm mã HTTP 4xx/5xx -> axios ném trước khi unwrap() kịp chạy, khiến UI
// hiện "Request failed with status code 415" thay vì câu tiếng Việt. Đổi message về đúng envelope.
api.interceptors.response.use(undefined, (err) => {
  const msg = err?.response?.data?.error;
  if (typeof msg === "string" && msg) err.message = msg;
  return Promise.reject(err);
});

export interface Envelope<T> { success: boolean; data: T; error: string | null; }

export function unwrap<T>(resp: { data: Envelope<T> }): T {
  if (!resp.data.success) throw new Error(resp.data.error ?? "Lỗi không xác định");
  return resp.data.data;
}
