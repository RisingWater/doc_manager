export interface DocItem {
  id: number
  path: string
  file_name: string
  ext: string
  size: number
  mtime: string | null
  rel_dir: string
  year: string | null
  subject: string | null
  city: string | null
  exam: string | null
  paper_type: string
  is_classified: boolean
  missing_dims: string[]
}

export interface OptionItem {
  value: string
  count: number
}

export interface MetaOptions {
  years: OptionItem[]
  subjects: OptionItem[]
  cities: OptionItem[]
  exams: OptionItem[]
  paper_types: OptionItem[]
  total: number
  classified: number
}

export interface ScanLog {
  id: number
  trigger_type: string
  status: string
  started_at: string
  finished_at: string | null
  files_found: number
  files_added: number
  files_skipped: number
  message: string | null
}

export interface DocQuery {
  years?: string[]
  subjects?: string[]
  cities?: string[]
  exams?: string[]
  paper_type?: string[]
  classified?: string
  q?: string
  sort?: string
  page: number
  pageSize: number
}

export interface DirInfo {
  path: string
  exists: boolean
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const data = await res.json()
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

function toQuery(params: Record<string, string | number | string[] | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) continue
    sp.set(k, Array.isArray(v) ? v.join(',') : String(v))
  }
  return sp.toString()
}

export const api = {
  options: () => http<MetaOptions>('/api/meta/options'),

  documents: (query: DocQuery) =>
    http<{ total: number; page: number; page_size: number; items: DocItem[] }>(
      `/api/documents?${toQuery({ ...query })}`,
    ),

  scanStatus: () =>
    http<{ running: boolean; scan_id: number | null; last: ScanLog | null }>('/api/scan/status'),

  scanLogs: (limit = 20) => http<ScanLog[]>(`/api/scan/logs?limit=${limit}`),

  startScan: () =>
    http<{ ok: boolean; scan_id?: number; message?: string }>('/api/scan', { method: 'POST' }),

  dirs: () => http<DirInfo[]>('/api/dirs'),
}

export function downloadDoc(id: number) {
  const a = document.createElement('a')
  a.href = `/api/documents/${id}/download`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export interface UploadFields {
  year: string
  subject: string
  city: string
  exam: string
  root_dir: string
}

export function uploadDoc(
  file: File,
  fields: UploadFields,
  onProgress?: (percent: number) => void,
): Promise<{ ok: boolean; id: number; path: string; file_name: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/upload')
    const fd = new FormData()
    fd.append('file', file)
    Object.entries(fields).forEach(([k, v]) => fd.append(k, v ?? ''))
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          reject(new Error('响应解析失败'))
        }
      } else {
        let msg = `HTTP ${xhr.status}`
        try {
          const data = JSON.parse(xhr.responseText)
          msg = typeof data.detail === 'string' ? data.detail : msg
        } catch {
          /* ignore */
        }
        reject(new Error(msg))
      }
    }
    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.send(fd)
  })
}
