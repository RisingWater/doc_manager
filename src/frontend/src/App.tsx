import { useCallback, useEffect, useRef, useState, type Key } from 'react'
import {
  Alert,
  App as AntdApp,
  AutoComplete,
  Button,
  Card,
  Form,
  Input,
  Layout,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import {
  ClearOutlined,
  DownloadOutlined,
  FileTextOutlined,
  ReloadOutlined,
  ScanOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { api, downloadDoc, uploadDoc } from './api'
import type { DirInfo, DocItem, MetaOptions, OptionItem, ScanLog } from './api'

const DIM_NAMES: Record<string, string> = { year: '年份', subject: '科目', city: '地市', exam: '考试' }

interface FilterState {
  years: string[]
  subjects: string[]
  cities: string[]
  exams: string[]
  paperTypes: string[]
  classified: string
  q: string
}

const EMPTY_FILTERS: FilterState = { years: [], subjects: [], cities: [], exams: [], paperTypes: [], classified: '', q: '' }

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function fmtSize(size: number): string {
  if (!size) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = size
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

function toOpts(list: OptionItem[]) {
  return list.map((o) => ({ label: `${o.value} (${o.count})`, value: o.value }))
}

export default function App() {
  const { message } = AntdApp.useApp()
  const [options, setOptions] = useState<MetaOptions>({
    years: [], subjects: [], cities: [], exams: [], paper_types: [], total: 0, classified: 0,
  })
  const [filters, setFilters] = useState<FilterState>({ ...EMPTY_FILTERS })
  const [docs, setDocs] = useState<DocItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [sort, setSort] = useState('mtime_desc')
  const [selectedIds, setSelectedIds] = useState<Key[]>([])
  const [scanning, setScanning] = useState(false)
  const [lastLog, setLastLog] = useState<ScanLog | null>(null)
  const [dirWarning, setDirWarning] = useState('')
  const [dirs, setDirs] = useState<DirInfo[]>([])
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadForm] = Form.useForm()

  const loadOptions = useCallback(async () => {
    try {
      setOptions(await api.options())
    } catch (e) {
      console.error(e)
    }
  }, [])

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.documents({ ...filters, paper_type: filters.paperTypes, page, pageSize, sort })
      setDocs(res.items)
      setTotal(res.total)
    } catch (e) {
      message.error(`加载文档失败：${String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [filters, page, pageSize, sort, message])

  const loadDocsRef = useRef(loadDocs)
  useEffect(() => {
    loadDocsRef.current = loadDocs
  }, [loadDocs])

  const pollScan = useCallback(async () => {
    setScanning(true)
    const deadline = Date.now() + 10 * 60 * 1000
    try {
      while (Date.now() < deadline) {
        await sleep(1000)
        const st = await api.scanStatus()
        if (st.last) setLastLog(st.last)
        if (!st.running) {
          const log = st.last
          if (log?.status === 'finished') {
            message.success(`扫描完成：发现 ${log.files_found} 个，新增 ${log.files_added} 个，跳过 ${log.files_skipped} 个`)
          } else if (log) {
            message.error(`扫描失败：${log.message ?? '未知错误'}`)
          }
          break
        }
      }
    } catch (e) {
      message.error(`查询扫描状态失败：${String(e)}`)
    } finally {
      setScanning(false)
      await Promise.all([loadOptions(), loadDocsRef.current()])
    }
  }, [message, loadOptions])

  useEffect(() => {
    void loadOptions()
    void (async () => {
      try {
        const list = await api.dirs()
        setDirs(list)
        if (list.length === 0) {
          setDirWarning('docs.json 未配置任何扫描目录，请编辑项目根目录下的 docs.json')
        } else {
          const missing = list.filter((d) => !d.exists).map((d) => d.path)
          if (missing.length) setDirWarning(`以下扫描目录不存在：${missing.join('、')}`)
        }
      } catch {
        /* ignore */
      }
      try {
        const st = await api.scanStatus()
        if (st.last) setLastLog(st.last)
        if (st.running) void pollScan()
      } catch {
        /* ignore */
      }
    })()
  }, [loadOptions, pollScan])

  useEffect(() => {
    void loadDocs()
  }, [loadDocs])

  const handleScan = async () => {
    try {
      const res = await api.startScan()
      if (!res.ok) {
        message.warning(res.message ?? '无法启动扫描')
        return
      }
      message.info('扫描已开始')
      await pollScan()
    } catch (e) {
      message.error(`启动扫描失败：${String(e)}`)
    }
  }

  const updateFilter = (key: keyof FilterState, value: string | string[]) => {
    setPage(1)
    setFilters((f) => ({ ...f, [key]: value }))
  }

  const resetFilters = () => {
    setFilters({ ...EMPTY_FILTERS })
    setPage(1)
  }

  const handleBatchDownload = () => {
    if (selectedIds.length === 0) return
    message.info(`开始下载 ${selectedIds.length} 个文件`)
    docs
      .filter((d) => selectedIds.includes(d.id))
      .forEach((d, i) => {
        setTimeout(() => downloadDoc(d.id), i * 400)
      })
  }

  const defaultUploadDir = () => {
    const uploads = dirs.find((d) => /uploads\\?\/?$/i.test(d.path.replace(/\\/g, '/')))
    return uploads?.path ?? dirs[0]?.path ?? ''
  }

  const openUpload = () => {
    uploadForm.resetFields()
    uploadForm.setFieldsValue({ root_dir: defaultUploadDir(), year: '', subject: '', city: '', exam: '' })
    setUploadProgress(0)
    setUploadOpen(true)
  }

  const handleUploadSubmit = async () => {
    const values = await uploadForm.validateFields()
    const rawFile: File | undefined = values.file?.[0]?.originFileObj
    if (!rawFile) {
      message.warning('请选择要上传的文件')
      return
    }
    setUploading(true)
    setUploadProgress(0)
    try {
      const res = await uploadDoc(rawFile, {
        year: values.year ?? '',
        subject: values.subject ?? '',
        city: values.city ?? '',
        exam: values.exam ?? '',
        root_dir: values.root_dir ?? '',
      }, setUploadProgress)
      message.success(`上传成功：${res.file_name}`)
      setUploadOpen(false)
      await Promise.all([loadOptions(), loadDocsRef.current()])
    } catch (e) {
      message.error(`上传失败：${String(e)}`)
    } finally {
      setUploading(false)
    }
  }

  const autoOptions = (list: OptionItem[]) => list.map((o) => ({ value: o.value }))

  const columns: ColumnsType<DocItem> = [
    {
      title: '文件名',
      dataIndex: 'file_name',
      width: 320,
      ellipsis: { showTitle: false },
      sorter: true,
      render: (v: string, r) => (
        <Tooltip title={r.path} placement="topLeft">
          <span>{v}</span>
        </Tooltip>
      ),
    },
    { title: '年份', dataIndex: 'year', width: 90, render: (v) => v ?? '-' },
    { title: '科目', dataIndex: 'subject', width: 90, render: (v) => v ?? '-' },
    { title: '地市', dataIndex: 'city', width: 100, render: (v) => v ?? '-' },
    { title: '考试', dataIndex: 'exam', width: 110, render: (v) => v ?? '-' },
    {
      title: '试卷/答案',
      dataIndex: 'paper_type',
      width: 110,
      render: (v: string) => (
        <Tag color={v === '答案' ? 'green' : v === '试卷+答案' ? 'purple' : 'blue'}>{v}</Tag>
      ),
    },
    {
      title: '分类状态',
      dataIndex: 'is_classified',
      width: 100,
      render: (v: boolean, r) =>
        v ? (
          <Tag color="success">已分类</Tag>
        ) : (
          <Tooltip title={`缺少：${r.missing_dims.map((d) => DIM_NAMES[d] ?? d).join('、') || '未知'}`}>
            <Tag color="warning" style={{ cursor: 'default' }}>未分类</Tag>
          </Tooltip>
        ),
    },
    { title: '大小', dataIndex: 'size', width: 100, render: (v: number) => fmtSize(v) },
    {
      title: '修改时间',
      dataIndex: 'mtime',
      width: 170,
      sorter: true,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, r) => (
        <Button type="link" size="small" icon={<DownloadOutlined />} onClick={() => downloadDoc(r.id)}>
          下载
        </Button>
      ),
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#001529',
          paddingInline: 24,
        }}
      >
        <Space>
          <FileTextOutlined style={{ color: '#fff', fontSize: 20 }} />
          <Typography.Title level={4} style={{ color: '#fff', margin: 0 }}>
            试卷文档管理系统
          </Typography.Title>
        </Space>
        <Space>
          {lastLog && (
            <Typography.Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>
              上次扫描 {lastLog.finished_at ?? lastLog.started_at}（{lastLog.trigger_type === 'manual' ? '手动' : '自动'}）
              新增 {lastLog.files_added} / 跳过 {lastLog.files_skipped}
            </Typography.Text>
          )}
          <Button type="primary" icon={<ScanOutlined />} loading={scanning} onClick={handleScan}>
            {scanning ? '扫描中…' : '立即扫描'}
          </Button>
        </Space>
      </Layout.Header>
      <Layout.Content style={{ padding: 24 }}>
        <div style={{ maxWidth: 1400, margin: '0 auto' }}>
          {dirWarning && (
            <Alert type="warning" showIcon message={dirWarning} style={{ marginBottom: 16 }} />
          )}
          <Card>
            <Space wrap style={{ marginBottom: 12 }}>
              <Select
                mode="multiple"
                placeholder="年份"
                style={{ minWidth: 160 }}
                maxTagCount="responsive"
                allowClear
                options={toOpts(options.years)}
                value={filters.years}
                onChange={(v) => updateFilter('years', v)}
              />
              <Select
                mode="multiple"
                placeholder="科目"
                style={{ minWidth: 140 }}
                maxTagCount="responsive"
                allowClear
                options={toOpts(options.subjects)}
                value={filters.subjects}
                onChange={(v) => updateFilter('subjects', v)}
              />
              <Select
                mode="multiple"
                placeholder="地市"
                style={{ minWidth: 150 }}
                maxTagCount="responsive"
                allowClear
                options={toOpts(options.cities)}
                value={filters.cities}
                onChange={(v) => updateFilter('cities', v)}
              />
              <Select
                mode="multiple"
                placeholder="考试"
                style={{ minWidth: 150 }}
                maxTagCount="responsive"
                allowClear
                options={toOpts(options.exams)}
                value={filters.exams}
                onChange={(v) => updateFilter('exams', v)}
              />
              <Select
                mode="multiple"
                placeholder="试卷/答案"
                style={{ minWidth: 140 }}
                maxTagCount="responsive"
                allowClear
                options={toOpts(options.paper_types)}
                value={filters.paperTypes}
                onChange={(v) => updateFilter('paperTypes', v)}
              />
              <Select
                placeholder="分类状态"
                style={{ minWidth: 120 }}
                allowClear
                options={[
                  { label: '全部', value: '' },
                  { label: '已分类', value: 'yes' },
                  { label: '未分类', value: 'no' },
                ]}
                value={filters.classified}
                onChange={(v) => updateFilter('classified', v ?? '')}
              />
            </Space>
            <Space wrap style={{ marginBottom: 16 }}>
              <Input.Search
                placeholder="模糊搜索：文件名 / 路径 / 分类"
                style={{ width: 280 }}
                allowClear
                enterButton
                onSearch={(v) => {
                  setPage(1)
                  setFilters((f) => ({ ...f, q: v.trim() }))
                }}
              />
              <Button
                icon={<ReloadOutlined />}
                onClick={() => {
                  void loadOptions()
                  void loadDocs()
                }}
              >
                刷新
              </Button>
              <Button icon={<ClearOutlined />} onClick={resetFilters}>
                重置
              </Button>
              <Button icon={<UploadOutlined />} onClick={openUpload}>
                上传文档
              </Button>
              {selectedIds.length > 0 && (
                <Button type="primary" icon={<DownloadOutlined />} onClick={handleBatchDownload}>
                  批量下载 ({selectedIds.length})
                </Button>
              )}
            </Space>
            <Table<DocItem>
              rowKey="id"
              size="middle"
              loading={loading}
              columns={columns}
              dataSource={docs}
              rowSelection={{
                selectedRowKeys: selectedIds,
                onChange: (keys) => setSelectedIds(keys),
              }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                showTotal: (t) => `共 ${t} 个文件`,
                onChange: (p, ps) => {
                  setPage(p)
                  setPageSize(ps)
                },
              }}
              onChange={(_pag, _filters, sorter) => {
                const s = Array.isArray(sorter) ? sorter[0] : sorter
                if (!s?.order) return
                if (s.field === 'mtime') setSort(s.order === 'ascend' ? 'mtime_asc' : 'mtime_desc')
                if (s.field === 'file_name') setSort(s.order === 'ascend' ? 'name_asc' : 'name_desc')
              }}
              scroll={{ x: 1100 }}
            />
          </Card>
        </div>
      </Layout.Content>
      <Modal
        title="上传文档"
        open={uploadOpen}
        onOk={handleUploadSubmit}
        onCancel={() => !uploading && setUploadOpen(false)}
        confirmLoading={uploading}
        okText="上传"
        cancelText="取消"
        maskClosable={false}
        width={520}
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item name="file" label="文件" valuePropName="fileList" getValueFromEvent={(e) => e?.fileList ?? []} rules={[{ required: true, message: '请选择文件' }]}>
            <Upload beforeUpload={() => false} maxCount={1} disabled={uploading}>
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="root_dir" label="保存目录（docs.json 中配置的目录）">
            <Select
              allowClear
              placeholder="默认 uploads"
              options={dirs.map((d) => ({ label: d.path, value: d.path }))}
              disabled={uploading}
            />
          </Form.Item>
          <Form.Item name="year" label="年份">
            <AutoComplete options={autoOptions(options.years)} placeholder="如 2023（可留空）" disabled={uploading} />
          </Form.Item>
          <Form.Item name="subject" label="科目">
            <AutoComplete options={autoOptions(options.subjects)} placeholder="如 数学（可留空）" disabled={uploading} />
          </Form.Item>
          <Form.Item name="city" label="地市">
            <AutoComplete options={autoOptions(options.cities)} placeholder="如 福州市（可留空）" disabled={uploading} />
          </Form.Item>
          <Form.Item name="exam" label="考试">
            <AutoComplete options={autoOptions(options.exams)} placeholder="如 一检 / 中考（可留空）" disabled={uploading} />
          </Form.Item>
          {uploading && (
            <Typography.Text type="secondary">上传进度：{uploadProgress}%</Typography.Text>
          )}
        </Form>
      </Modal>
    </Layout>
  )
}
