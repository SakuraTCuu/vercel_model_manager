"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { v4 as uuidv4 } from 'uuid';

function getDefaultOrderId() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const h = String(now.getHours()).padStart(2, "0");
  return `${y}-${m}-${d} ${h}`;
}

function parseDate(str: string) {
  // 兼容 "2024-05-01 14:23" 格式
  return new Date(str.replace(/-/g, "/"));
}

const TABS = [
  { key: "log", label: "请求日志" },
  { key: "add", label: "新增 API Key" },
  { key: "manage", label: "管理 API Key" },
  { key: "model", label: "模型管理" },
  { key: "whitelist", label: "白名单管理" },
];

function DashboardPage() {
  // 表单状态
  const [activeTab, setActiveTab] = useState("log");
  const [buyer, setBuyer] = useState("");
  const [model, setModel] = useState("");
  const [platform, setPlatform] = useState("");
  const [amount, setAmount] = useState("");
  const [remark, setRemark] = useState("");
  const [createdAt, setCreatedAt] = useState(() => formatDateTime(new Date()));

  // 模型管理相关状态
  type Model = {
    id: number;
    name: string;
    label: string;
    platform: string;
    price: string;
    decryptSecret: string;
    size: string;
    createdAt: string;
    description?: string;
  };
  const [models, setModels] = useState<Model[]>([]);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelPage, setModelPage] = useState(1);
  const modelPageSize = 10;
  const [modelTotal, setModelTotal] = useState(0);
  const [showModelModal, setShowModelModal] = useState(false);
  const [editModel, setEditModel] = useState<Model | null>(null);
  const [modelModalLoading, setModelModalLoading] = useState(false);
  const [modelModalError, setModelModalError] = useState("");
  const [deleteModelId, setDeleteModelId] = useState<number | null>(null);
  const modelFormRef = useRef<HTMLFormElement>(null);

  // 格式化时间为 年-月-日 时-分-秒
  function formatDateTime(date: Date | string) {
    const d = typeof date === 'string' ? new Date(date) : date;
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    const s = String(d.getSeconds()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}:${s}`;
  }

  const [modalInfo, setModalInfo] = useState<any | null>(null);
  const [newKey, setNewKey] = useState<any | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [saving, setSaving] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  // 数据加载相关
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // 新增：分页状态
  const [page, setPage] = useState(1);
  const pageSize = 10;
  // 按请求时间降序排序
  const totalPages = Math.ceil(total / pageSize);
  const pagedApiKeys = apiKeys;

  // 详情弹窗状态
  const [detailItem, setDetailItem] = useState<null | typeof apiKeys[0]>(null);

  // 删除确认弹窗状态
  const [deleteId, setDeleteId] = useState<number | null>(null);

  // 编辑弹窗状态
  const [editItem, setEditItem] = useState<any | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState("");

  // mock 模型列表和价格
  // mockApiKeys、modelOptions、platformOptions 等 mock 数据全部移除
  // API Key、模型、日志、白名单等所有数据都通过接口获取，已在各自 fetch 函数实现
  // Tab 切换时自动请求接口，已在 useEffect 中实现

  // 选择模型时自动填充金额和平台
  const [modelId, setModelId] = useState<number | null>(null);
  function handleModelChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    setModelId(val ? Number(val) : null);
    const found = models.find(m => m.id === Number(val));
    setModel(found ? found.name : "");
    setAmount(found ? found.price : "");
    setPlatform(found ? found.platform : "");
  }

  // 新增 API Key
  async function handleGenerateKey(e: React.FormEvent) {
    e.preventDefault();
    if (!buyer || !modelId || !amount) {
      setError("请填写所有必填项");
      return;
    }
    setError("");
    setSaving(true);
    const foundModel = models.find(m => m.id === modelId);
    const key = uuidv4().replace(/-/g, ''); // 32位uuid
    const newItem = {
      buyer,
      modelId,
      platform: foundModel ? foundModel.platform : platform,
      amount,
      mac: `AA:BB:CC:DD:EE:${Math.floor(Math.random()*90+10)}`,
      lastRequest: createdAt,
      requestCount: 0,
      ip: "127.0.0.1",
      status: true,
      remark,
      key,
    };
    const res = await fetch("/api/apikey", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newItem),
    });
    setSaving(false);
    if (res.ok) {
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
      const now = new Date();
      const info: any = {
        buyer: newItem.buyer,
        createdAt: formatDateTime(now),
        model: foundModel ? foundModel.label : '',
        platform: newItem.platform,
        amount: newItem.amount,
        remark: newItem.remark,
        key: newItem.key,
      };
      setModalInfo(info);
      setNewKey(info);
      setBuyer("");
      setModelId(null);
      setModel("");
      setPlatform("");
      setCreatedAt(formatDateTime(new Date()));
      setAmount("");
      setRemark("");
      setPage(1);
      fetchApiKeys(1);
    } else {
      setError("保存失败，请重试");
    }
  }

  // 加载列表数据
  async function fetchApiKeys(page: number) {
    setLoading(true);
    const res = await fetch(`/api/apikey?page=${page}&pageSize=10`);
    const data = await res.json();
    setApiKeys(data.data);
    setTotal(data.total);
    setLoading(false);
  }

  // 加载模型列表
  async function fetchModels() {
    setModelLoading(true);
    const res = await fetch("/api/model");
    const data = await res.json();
    setModels(data);
    setModelTotal(data.length);
    setModelLoading(false);
  }

  // 请求日志相关状态
  type LogItem = {
    id: number;
    key: string;
    mac: string;
    cpu: string;
    ip: string;
    time: string;
    status: string; // "正常" | "异常"
    error?: string;
  };
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logLoading, setLogLoading] = useState(false);
  const [logPage, setLogPage] = useState(1);
  const logPageSize = 10;
  const [logTotal, setLogTotal] = useState(0);

  // mock 日志数据
  // 加载日志数据（改为接口）
  async function fetchLogs(page: number) {
    setLogLoading(true);
    try {
      const res = await fetch(`/api/apikey-log?page=${page}&pageSize=${logPageSize}`);
      const result = await res.json();
      setLogs(result.data);
      setLogTotal(result.total);
    } catch (e) {
      setLogs([]);
      setLogTotal(0);
    }
    setLogLoading(false);
  }

  useEffect(() => {
    if (activeTab === "log") {
      fetchLogs(logPage);
    }
  }, [activeTab, logPage]);

  useEffect(() => {
    if (activeTab === "add" || activeTab === "manage") {
      fetchApiKeys(page);
    }
  }, [activeTab, page]);

  useEffect(() => {
    if (activeTab === "model") {
      fetchModels();
    }
  }, [activeTab]);

  // 激活/停用
  async function toggleStatus(id: number, status: boolean) {
    await fetch("/api/apikey", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, status: !status }),
    });
    fetchApiKeys(page);
  }
  // 删除
  async function deleteKey(id: number) {
    await fetch("/api/apikey", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setDeleteId(null);
    fetchApiKeys(page);
  }

  // 新增/编辑模型
  async function handleModelModalSubmit(e: React.FormEvent) {
    e.preventDefault();
    setModelModalLoading(true);
    setModelModalError("");
    const form = e.target as typeof e.target & {
      name: { value: string };
      label: { value: string };
      platform: { value: string };
      price: { value: string };
      decryptSecret: { value: string };
      size: { value: string };
      description: { value: string };
    };
    const body = {
      name: form.name.value,
      label: form.label.value,
      platform: form.platform.value,
      price: form.price.value,
      decryptSecret: form.decryptSecret.value,
      size: form.size.value,
      description: form.description.value,
    };
    let ok = false;
    if (editModel) {
      const res = await fetch("/api/model", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: editModel.id, ...body }),
      });
      ok = res.ok;
    } else {
      const res = await fetch("/api/model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      ok = res.ok;
    }
    setModelModalLoading(false);
    if (ok) {
      setShowModelModal(false);
      setEditModel(null);
      fetchModels();
    } else {
      setModelModalError("保存失败，请重试");
    }
  }

  // 删除模型
  async function handleDeleteModel(id: number) {
    await fetch("/api/model", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setDeleteModelId(null);
    fetchModels();
  }

  // 白名单管理相关状态
  const [whitelists, setWhitelists] = useState<any[]>([]);
  const [whitelistLoading, setWhitelistLoading] = useState(false);
  const [whitelistPage, setWhitelistPage] = useState(1);
  const whitelistPageSize = 10;
  const [whitelistTotal, setWhitelistTotal] = useState(0);
  const [editWhitelist, setEditWhitelist] = useState<any | null>(null);
  const [editWhitelistRemark, setEditWhitelistRemark] = useState("");
  const [editWhitelistLoading, setEditWhitelistLoading] = useState(false);
  const [deleteWhitelistId, setDeleteWhitelistId] = useState<number | null>(null);

  // 加载白名单
  async function fetchWhitelists(page: number) {
    setWhitelistLoading(true);
    try {
      const res = await fetch(`/api/whitelist?page=${page}&pageSize=${whitelistPageSize}`);
      const result = await res.json();
      setWhitelists(result.data);
      setWhitelistTotal(result.total);
    } catch (e) {
      setWhitelists([]);
      setWhitelistTotal(0);
    }
    setWhitelistLoading(false);
  }

  useEffect(() => {
    if (activeTab === "whitelist") {
      fetchWhitelists(whitelistPage);
    }
  }, [activeTab, whitelistPage]);

  // 新增白名单
  async function handleAddWhitelist(apiKeyId: number) {
    await fetch("/api/whitelist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKeyId }),
    });
    fetchWhitelists(1);
  }
  // 编辑白名单备注
  async function handleEditWhitelistRemark() {
    if (!editWhitelist) return;
    setEditWhitelistLoading(true);
    await fetch("/api/whitelist", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: editWhitelist.id, remark: editWhitelistRemark }),
    });
    setEditWhitelistLoading(false);
    setEditWhitelist(null);
    setEditWhitelistRemark("");
    fetchWhitelists(whitelistPage);
  }
  // 删除白名单
  async function handleDeleteWhitelist(id: number) {
    await fetch("/api/whitelist", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    setDeleteWhitelistId(null);
    fetchWhitelists(whitelistPage);
  }

  const [showAddWhitelistModal, setShowAddWhitelistModal] = useState(false);
  const [addWhitelistKeyId, setAddWhitelistKeyId] = useState<number | null>(null);
  const [addWhitelistRemark, setAddWhitelistRemark] = useState("");
  const [addWhitelistLoading, setAddWhitelistLoading] = useState(false);
  const [availableKeys, setAvailableKeys] = useState<any[]>([]);

  // 加载未在白名单的API Key
  async function fetchAvailableKeys() {
    // 获取所有API Key和白名单
    const [keyRes, whitelistRes] = await Promise.all([
      fetch("/api/apikey?page=1&pageSize=1000"),
      fetch("/api/whitelist?page=1&pageSize=1000")
    ]);
    const keyData = await keyRes.json();
    const whitelistData = await whitelistRes.json();
    const whitelistKeyIds = new Set(whitelistData.data.map((w: any) => w.key));
    // 只保留未在白名单的key
    setAvailableKeys(keyData.data.filter((k: any) => !whitelistKeyIds.has(k.key)));
  }

  // 添加白名单（弹窗用）
  async function handleAddWhitelistModal() {
    if (!addWhitelistKeyId) return;
    setAddWhitelistLoading(true);
    await fetch("/api/whitelist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKeyId: addWhitelistKeyId, remark: addWhitelistRemark }),
    });
    setAddWhitelistLoading(false);
    setShowAddWhitelistModal(false);
    setAddWhitelistKeyId(null);
    setAddWhitelistRemark("");
    fetchWhitelists(1);
  }

  const router = useRouter();
  // 登录守卫
  useEffect(() => {
    if (typeof window !== "undefined") {
      const isLogin = document.cookie.split('; ').find(row => row.startsWith('isLogin='));
      if (!isLogin || isLogin.split('=')[1] !== 'true') {
        router.replace("/login");
      }
    }
  }, [router]);

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* 左侧导航栏 */}
      <aside className="w-56 bg-white border-r flex flex-col py-8 px-4">
        <h2 className="text-xl font-bold mb-8 text-center">API Key 管理</h2>
        <nav className="flex flex-col gap-2">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`text-left px-4 py-2 rounded transition font-medium ${
                activeTab === tab.key
                  ? "bg-blue-600 text-white"
                  : "hover:bg-blue-100 text-gray-700"
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
        {/* 右上角退出登录按钮 */}
        <button
          className="mt-8 w-full bg-gray-200 hover:bg-gray-300 text-gray-700 py-2 rounded"
          onClick={() => {
            document.cookie = 'isLogin=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            router.replace('/login');
          }}
        >退出登录</button>
      </aside>
      {/* 右侧内容区 */}
      <main className="flex-1 p-10">
        {activeTab === "log" && (
          <div className="w-full bg-white p-6 rounded shadow min-h-[300px]">
            <h3 className="text-xl font-bold mb-6 text-left">请求日志</h3>
            {logLoading ? (
              <div className="flex items-center justify-center h-40 text-blue-600 text-lg">数据加载中...</div>
            ) : logs.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-gray-400 text-lg">暂无日志数据</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="p-2 text-center">Key</th>
                        <th className="p-2 text-center">MAC</th>
                        <th className="p-2 text-center">CPU</th>
                        <th className="p-2 text-center">IP</th>
                        <th className="p-2 text-center">时间</th>
                        <th className="p-2 text-center">状态</th>
                        <th className="p-2 text-center">异常</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map(item => (
                        <tr key={item.id} className={item.status === "异常" ? "bg-red-50" : ""}>
                          <td className="p-2 text-center break-all max-w-[180px]">{item.key}</td>
                          <td className="p-2 text-center">{item.mac}</td>
                          <td className="p-2 text-center">{item.cpu}</td>
                          <td className="p-2 text-center">{item.ip}</td>
                          <td className="p-2 text-center">{item.time}</td>
                          <td className={`p-2 text-center font-bold ${item.status === "异常" ? "text-red-600" : "text-green-600"}`}>{item.status}</td>
                          <td className={`p-2 text-center ${item.status === "异常" ? "text-red-600 font-bold" : "text-gray-400"}`}>{item.error || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* 分页控件 */}
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-gray-500">共 {logTotal} 条，{logPage}/{Math.ceil(logTotal/logPageSize)} 页</div>
                  <div className="flex gap-2">
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setLogPage(p => Math.max(1, p - 1))}
                      disabled={logPage === 1}
                    >上一页</button>
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setLogPage(p => Math.min(Math.ceil(logTotal/logPageSize), logPage + 1))}
                      disabled={logPage === Math.ceil(logTotal/logPageSize)}
                    >下一页</button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
        {activeTab === "add" && (
          <div className="max-w-md mx-auto bg-white p-8 rounded shadow">
            <h3 className="text-xl font-bold mb-6">新增 API Key</h3>
            <form onSubmit={handleGenerateKey}>
              {saving && <div className="mb-4 text-blue-600 bg-blue-50 border border-blue-200 rounded px-4 py-2 text-center">保存中...</div>}
              {success && <div className="mb-4 text-green-600 bg-green-50 border border-green-200 rounded px-4 py-2 text-center">保存成功</div>}
              {error && <div className="mb-4 text-red-500 text-sm">{error}</div>}
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">买家昵称 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
                  value={buyer}
                  onChange={e => setBuyer(e.target.value)}
                  placeholder="请输入买家昵称"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">模型 <span className="text-red-500">*</span></label>
                <select
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
                  value={modelId ?? ''}
                  onChange={handleModelChange}
                  required
                >
                  <option value="">请选择模型</option>
                  {models.map(opt => (
                    <option key={opt.id} value={opt.id}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">使用平台 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border rounded bg-gray-100 text-gray-500"
                  value={platform}
                  readOnly
                  required
                  placeholder="请先选择模型"
                />
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">创建时间</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border rounded bg-gray-100 text-gray-500"
                  value={createdAt}
                  readOnly
                />
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">金额 <span className="text-red-500">*</span></label>
                <input
                  type="number"
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
                  value={amount}
                  onChange={e => setAmount(e.target.value)}
                  placeholder="请输入金额"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">备注</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
                  value={remark}
                  onChange={e => setRemark(e.target.value)}
                  placeholder="可选，备注信息"
                />
              </div>
              <button
                type="submit"
                className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition"
              >
                生成 API Key
              </button>
            </form>
            {newKey && (
              <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded text-green-700 break-all">
                <div className="font-bold mb-2">填写信息：</div>
                <div className="mb-1"><span className="font-semibold">玩家昵称：</span>{newKey.buyer}</div>
                <div className="mb-1"><span className="font-semibold">创建时间：</span>{newKey.createdAt || '-'}</div>
                <div className="mb-1"><span className="font-semibold">购买模型：</span>{newKey.model}</div>
                <div className="mb-1"><span className="font-semibold">使用平台：</span>{newKey.platform}</div>
                <div className="mb-1"><span className="font-semibold">金额：</span>{newKey.amount}</div>
                <div className="mb-1"><span className="font-semibold">备注：</span>{newKey.remark || "-"}</div>
                <div className="mb-1"><span className="font-semibold">Key：</span>{newKey.key}</div>
              </div>
            )}
            {/* 新增成功后弹出模态框 */}
            {modalInfo && (
              <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
                  <button
                    className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                    onClick={() => setModalInfo(null)}
                  >×</button>
                  <h4 className="text-lg font-bold mb-4">API Key 信息</h4>
                  <div className="mb-2"><span className="font-semibold">玩家昵称：</span>{modalInfo.buyer}</div>
                  <div className="mb-2"><span className="font-semibold">创建时间：</span>{modalInfo.createdAt || '-'}</div>
                  <div className="mb-2"><span className="font-semibold">购买模型：</span>{modalInfo.model}</div>
                  <div className="mb-2"><span className="font-semibold">使用平台：</span>{modalInfo.platform}</div>
                  <div className="mb-2"><span className="font-semibold">金额：</span>{modalInfo.amount}</div>
                  <div className="mb-2"><span className="font-semibold">备注：</span>{modalInfo.remark || "-"}</div>
                  <div className="mb-2 flex items-center"><span className="font-semibold">Key：</span>
                    <span className="break-all select-all">{modalInfo.key}</span>
                    <button
                      className="ml-2 px-2 py-1 rounded text-xs bg-gray-200 hover:bg-gray-300 border"
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(modalInfo.key);
                        setCopySuccess(true);
                        setTimeout(() => setCopySuccess(false), 2000);
                      }}
                    >复制</button>
                  </div>
                  {copySuccess && (
                    <div className="absolute left-1/2 -top-8 -translate-x-1/2 bg-green-50 border border-green-200 text-green-700 px-4 py-1 rounded shadow text-sm">复制成功</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        {activeTab === "manage" && (
          <div className="w-full bg-white p-6 rounded shadow min-h-[300px]">
            <h3 className="text-xl font-bold mb-6 text-left">API Key 列表</h3>
            {loading ? (
              <div className="flex items-center justify-center h-40 text-blue-600 text-lg">数据加载中...</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="p-2 text-center">玩家昵称</th>
                        <th className="p-2 text-center">模型</th>
                        <th className="p-2 text-center">创建时间</th>
                        <th className="p-2 text-center">请求次数</th>
                        <th className="p-2 text-center">IP</th>
                        <th className="p-2 text-center">状态</th>
                        <th className="p-2 text-center">Key</th>
                        <th className="p-2 text-right min-w-[140px]">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedApiKeys.map(item => (
                        <tr key={item.id} className="border-b">
                          <td className="p-2 text-center whitespace-nowrap">{item.buyer}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.model}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.createdAt ? formatDateTime(item.createdAt) : '-'}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.requestCount}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.ip}</td>
                          <td className="p-2 text-center whitespace-nowrap">
                            <span className={item.status ? "text-green-600" : "text-gray-400"}>
                              {item.status ? "激活" : "停用"}
                            </span>
                          </td>
                          <td className="p-2 text-center whitespace-nowrap break-all max-w-[180px]">{item.key}</td>
                          <td className="p-2 whitespace-nowrap">
                            <div className="flex gap-2 justify-end min-w-[140px]">
                              <button
                                className={`px-2 py-1 rounded text-xs ${item.status ? "bg-gray-200 hover:bg-gray-300" : "bg-green-200 hover:bg-green-300"}`}
                                onClick={() => toggleStatus(item.id, item.status)}
                              >
                                {item.status ? "停用" : "激活"}
                              </button>
                              <button
                                className="px-2 py-1 rounded text-xs bg-red-200 hover:bg-red-300"
                                onClick={() => setDeleteId(item.id)}
                              >
                                删除
                              </button>
                              <button
                                className="px-2 py-1 rounded text-xs bg-blue-200 hover:bg-blue-300"
                                onClick={() => setDetailItem(item)}
                              >
                                详情
                              </button>
                              <button
                                className="px-2 py-1 rounded text-xs bg-yellow-200 hover:bg-yellow-300"
                                onClick={() => setEditItem(item)}
                              >
                                编辑
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* 分页控件 */}
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-gray-500">共 {total} 条，{page}/{totalPages} 页</div>
                  <div className="flex gap-2">
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >上一页</button>
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                    >下一页</button>
                  </div>
                </div>
                {/* 详情弹窗 */}
                {detailItem && (
                  <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                    <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
                      <button
                        className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                        onClick={() => setDetailItem(null)}
                      >×</button>
                      <h4 className="text-lg font-bold mb-4">API Key 详情</h4>
                      <div className="mb-2"><span className="font-semibold">玩家昵称：</span>{detailItem.buyer}</div>
                      <div className="mb-2"><span className="font-semibold">模型：</span>{detailItem.model}</div>
                      <div className="mb-2"><span className="font-semibold">平台：</span>{detailItem.platform}</div>
                      <div className="mb-2"><span className="font-semibold">金额：</span>{detailItem.amount}</div>
                      <div className="mb-2"><span className="font-semibold">MAC：</span>{detailItem.mac}</div>
                      <div className="mb-2"><span className="font-semibold">备注：</span>{detailItem.remark || "-"}</div>
                      <div className="mb-2"><span className="font-semibold">Key：</span>{detailItem.key}</div>
                      <div className="mb-2"><span className="font-semibold">请求时间：</span>{detailItem.lastRequest}</div>
                      <div className="mb-2"><span className="font-semibold">请求次数：</span>{detailItem.requestCount}</div>
                      <div className="mb-2"><span className="font-semibold">IP：</span>{detailItem.ip}</div>
                      <div className="mb-2"><span className="font-semibold">状态：</span>{detailItem.status ? "激活" : "停用"}</div>
                      <div className="mt-4 flex justify-end">
                        <button
                          className="px-4 py-1 rounded bg-green-600 text-white hover:bg-green-700"
                          onClick={async () => {
                            await handleAddWhitelist(detailItem.id);
                            setDetailItem(null);
                          }}
                        >加入白名单</button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {activeTab === "model" && (
          <div className="w-full bg-white p-6 rounded shadow min-h-[300px]">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold text-left">模型管理</h3>
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                onClick={() => { setEditModel(null); setShowModelModal(true); }}
              >新增模型</button>
            </div>
            {modelLoading ? (
              <div className="flex items-center justify-center h-40 text-blue-600 text-lg">数据加载中...</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="p-2 text-center">名称</th>
                        <th className="p-2 text-center">展示名</th>
                        <th className="p-2 text-center">平台</th>
                        <th className="p-2 text-center">价格</th>
                        <th className="p-2 text-center">解密密钥</th>
                        <th className="p-2 text-center">大小</th>
                        <th className="p-2 text-center">描述</th>
                        <th className="p-2 text-center">创建时间</th>
                        <th className="p-2 text-right min-w-[120px]">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {models.slice((modelPage-1)*modelPageSize, modelPage*modelPageSize).map(item => (
                        <tr key={item.id} className="border-b">
                          <td className="p-2 text-center whitespace-nowrap">{item.name}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.label}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.platform}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.price}</td>
                          <td className="p-2 text-center whitespace-nowrap break-all max-w-[120px]">{item.decryptSecret}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.size}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.description || '-'}</td>
                          <td className="p-2 text-center whitespace-nowrap">{item.createdAt ? (typeof item.createdAt === 'string' ? item.createdAt.replace('T', ' ').slice(0, 19) : new Date(item.createdAt).toLocaleString()) : '-'}</td>
                          <td className="p-2 whitespace-nowrap flex gap-2 justify-end min-w-[120px]">
                            <button
                              className="px-2 py-1 rounded text-xs bg-yellow-200 hover:bg-yellow-300"
                              onClick={() => { setEditModel(item); setShowModelModal(true); }}
                            >编辑</button>
                            <button
                              className="px-2 py-1 rounded text-xs bg-red-200 hover:bg-red-300"
                              onClick={() => setDeleteModelId(item.id)}
                            >删除</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* 分页控件 */}
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-gray-500">共 {modelTotal} 条，{modelPage}/{Math.ceil(modelTotal/modelPageSize)} 页</div>
                  <div className="flex gap-2">
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setModelPage(p => Math.max(1, p - 1))}
                      disabled={modelPage === 1}
                    >上一页</button>
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setModelPage(p => Math.min(Math.ceil(modelTotal/modelPageSize), modelPage + 1))}
                      disabled={modelPage === Math.ceil(modelTotal/modelPageSize)}
                    >下一页</button>
                  </div>
                </div>
                {/* 删除确认弹窗 */}
                {deleteModelId !== null && (
                  <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                    <div className="bg-white rounded shadow-lg p-6 min-w-[280px] max-w-[90vw] relative">
                      <div className="text-lg font-bold mb-4">确认删除</div>
                      <div className="mb-6 text-gray-700">确定要删除该模型吗？此操作不可恢复。</div>
                      <div className="flex justify-end gap-4">
                        <button
                          className="px-4 py-1 rounded bg-gray-200 hover:bg-gray-300"
                          onClick={() => setDeleteModelId(null)}
                        >取消</button>
                        <button
                          className="px-4 py-1 rounded bg-red-500 text-white hover:bg-red-600"
                          onClick={() => handleDeleteModel(deleteModelId!)}
                        >确认删除</button>
                      </div>
                    </div>
                  </div>
                )}
                {/* 新增/编辑模型弹窗 */}
                {showModelModal && (
                  <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                    <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
                      <button
                        className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                        onClick={() => { setShowModelModal(false); setEditModel(null); }}
                      >×</button>
                      <h4 className="text-lg font-bold mb-4">{editModel ? '编辑模型' : '新增模型'}</h4>
                      <form ref={modelFormRef} onSubmit={handleModelModalSubmit}>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">英文唯一名 <span className="text-red-500">*</span></label>
                          <input name="name" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.name || ''} required />
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">展示名 <span className="text-red-500">*</span></label>
                          <input name="label" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.label || ''} required />
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">平台 <span className="text-red-500">*</span></label>
                          <select name="platform" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.platform ?? "兼容sd comfyui"} required>
                            <option value="">请选择平台</option>
                            <option value="sd">sd</option>
                            <option value="comfyui">comfyui</option>
                            <option value="兼容sd comfyui">兼容sd comfyui</option>
                          </select>
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">价格 <span className="text-red-500">*</span></label>
                          <input name="price" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.price || ''} required />
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">解密密钥 <span className="text-red-500">*</span></label>
                          <input name="decryptSecret" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.decryptSecret || ''} required />
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">大小 <span className="text-red-500">*</span></label>
                          <input name="size" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.size || ''} required />
                        </div>
                        <div className="mb-4">
                          <label className="block mb-1 text-gray-700">描述</label>
                          <input name="description" type="text" className="w-full px-3 py-2 border rounded" defaultValue={editModel?.description || ''} />
                        </div>
                        {modelModalError && <div className="mb-4 text-red-500 text-sm">{modelModalError}</div>}
                        <button
                          type="submit"
                          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition disabled:opacity-50"
                          disabled={modelModalLoading}
                        >
                          {modelModalLoading ? '保存中...' : '保存'}
                        </button>
                      </form>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {activeTab === "whitelist" && (
          <div className="w-full bg-white p-6 rounded shadow min-h-[300px]">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold text-left">白名单管理</h3>
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                onClick={async () => {
                  await fetchAvailableKeys();
                  setShowAddWhitelistModal(true);
                }}
              >添加白名单</button>
            </div>
            {whitelistLoading ? (
              <div className="flex items-center justify-center h-40 text-blue-600 text-lg">数据加载中...</div>
            ) : whitelists.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-gray-400 text-lg">暂无白名单数据</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="p-2 text-center">Key</th>
                        <th className="p-2 text-center">买家</th>
                        <th className="p-2 text-center">备注</th>
                        <th className="p-2 text-center">创建时间</th>
                        <th className="p-2 text-right min-w-[120px]">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {whitelists.map(item => (
                        <tr key={item.id} className="border-b">
                          <td className="p-2 text-center break-all max-w-[180px]">{item.key}</td>
                          <td className="p-2 text-center">{item.buyer}</td>
                          <td className="p-2 text-center">{item.remark || '-'}</td>
                          <td className="p-2 text-center">{typeof item.createdAt === 'string' ? item.createdAt.replace('T', ' ').slice(0, 19) : new Date(item.createdAt).toLocaleString()}</td>
                          <td className="p-2 whitespace-nowrap flex gap-2 justify-end min-w-[120px]">
                            <button
                              className="px-2 py-1 rounded text-xs bg-yellow-200 hover:bg-yellow-300"
                              onClick={() => { setEditWhitelist(item); setEditWhitelistRemark(item.remark || ''); }}
                            >编辑备注</button>
                            <button
                              className="px-2 py-1 rounded text-xs bg-red-200 hover:bg-red-300"
                              onClick={() => setDeleteWhitelistId(item.id)}
                            >删除</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* 分页控件 */}
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-gray-500">共 {whitelistTotal} 条，{whitelistPage}/{Math.ceil(whitelistTotal/whitelistPageSize)} 页</div>
                  <div className="flex gap-2">
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setWhitelistPage(p => Math.max(1, p - 1))}
                      disabled={whitelistPage === 1}
                    >上一页</button>
                    <button
                      className="px-3 py-1 rounded border bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                      onClick={() => setWhitelistPage(p => Math.min(Math.ceil(whitelistTotal/whitelistPageSize), whitelistPage + 1))}
                      disabled={whitelistPage === Math.ceil(whitelistTotal/whitelistPageSize)}
                    >下一页</button>
                  </div>
                </div>
                {/* 编辑备注弹窗 */}
                {editWhitelist && (
                  <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                    <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
                      <button
                        className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                        onClick={() => setEditWhitelist(null)}
                      >×</button>
                      <h4 className="text-lg font-bold mb-4">编辑备注</h4>
                      <input
                        type="text"
                        className="w-full px-3 py-2 border rounded mb-4"
                        value={editWhitelistRemark}
                        onChange={e => setEditWhitelistRemark(e.target.value)}
                        placeholder="请输入备注"
                      />
                      <div className="flex justify-end gap-4">
                        <button
                          className="px-4 py-1 rounded bg-gray-200 hover:bg-gray-300"
                          onClick={() => setEditWhitelist(null)}
                        >取消</button>
                        <button
                          className="px-4 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                          onClick={handleEditWhitelistRemark}
                          disabled={editWhitelistLoading}
                        >保存</button>
                      </div>
                    </div>
                  </div>
                )}
                {/* 删除确认弹窗 */}
                {deleteWhitelistId !== null && (
                  <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
                    <div className="bg-white rounded shadow-lg p-6 min-w-[280px] max-w-[90vw] relative">
                      <div className="text-lg font-bold mb-4">确认删除</div>
                      <div className="mb-6 text-gray-700">确定要删除该白名单吗？此操作不可恢复。</div>
                      <div className="flex justify-end gap-4">
                        <button
                          className="px-4 py-1 rounded bg-gray-200 hover:bg-gray-300"
                          onClick={() => setDeleteWhitelistId(null)}
                        >取消</button>
                        <button
                          className="px-4 py-1 rounded bg-red-500 text-white hover:bg-red-600"
                          onClick={() => handleDeleteWhitelist(deleteWhitelistId!)}
                        >确认删除</button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {/* 编辑弹窗 */}
        {editItem && (
          <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
            <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
              <button
                className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                onClick={() => setEditItem(null)}
              >×</button>
              <h4 className="text-lg font-bold mb-4">编辑 API Key</h4>
              <form
                onSubmit={async e => {
                  e.preventDefault();
                  setEditLoading(true);
                  setEditError("");
                  const form = e.target as typeof e.target & {
                    buyer: { value: string };
                    model: { value: string };
                    platform: { value: string };
                    amount: { value: string };
                    remark: { value: string };
                    status: { checked: boolean };
                  };
                  const patchData = {
                    id: editItem.id,
                    buyer: form.buyer.value,
                    model: form.model.value,
                    platform: form.platform.value,
                    amount: form.amount.value,
                    remark: form.remark.value,
                    status: form.status.checked,
                  };
                  const res = await fetch("/api/apikey", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(patchData),
                  });
                  setEditLoading(false);
                  if (res.ok) {
                    setEditItem(null);
                    fetchApiKeys(page);
                  } else {
                    setEditError("保存失败，请重试");
                  }
                }}
              >
                <div className="mb-4">
                  <label className="block mb-1 text-gray-700">买家昵称</label>
                  <input
                    name="buyer"
                    type="text"
                    className="w-full px-3 py-2 border rounded"
                    defaultValue={editItem.buyer}
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="block mb-1 text-gray-700">模型</label>
                  <select
                    name="model"
                    className="w-full px-3 py-2 border rounded"
                    defaultValue={editItem.model}
                    required
                  >
                    {/* modelOptions 移除，改为 models 列表 */}
                    {models.map(opt => (
                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div className="mb-4">
                  <label className="block mb-1 text-gray-700">平台</label>
                  <select
                    name="platform"
                    className="w-full px-3 py-2 border rounded"
                    defaultValue={editItem.platform}
                    required
                  >
                    {/* platformOptions 移除，改为 models 列表 */}
                    {models.map(opt => (
                      <option key={opt.id} value={opt.platform}>{opt.platform}</option>
                    ))}
                  </select>
                </div>
                <div className="mb-4">
                  <label className="block mb-1 text-gray-700">金额</label>
                  <input
                    name="amount"
                    type="number"
                    className="w-full px-3 py-2 border rounded"
                    defaultValue={editItem.amount}
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="block mb-1 text-gray-700">备注</label>
                  <input
                    name="remark"
                    type="text"
                    className="w-full px-3 py-2 border rounded"
                    defaultValue={editItem.remark}
                  />
                </div>
                <div className="mb-4 flex items-center gap-2">
                  <input
                    name="status"
                    type="checkbox"
                    className="mr-2"
                    defaultChecked={editItem.status}
                    id="edit-status"
                  />
                  <label htmlFor="edit-status" className="text-gray-700 select-none">激活</label>
                </div>
                {editError && <div className="mb-4 text-red-500 text-sm">{editError}</div>}
                <button
                  type="submit"
                  className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition disabled:opacity-50"
                  disabled={editLoading}
                >
                  {editLoading ? "保存中..." : "保存"}
                </button>
              </form>
            </div>
          </div>
        )}
        {/* 添加白名单弹窗 */}
        {showAddWhitelistModal && (
          <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
            <div className="bg-white rounded shadow-lg p-8 min-w-[320px] max-w-[90vw] relative">
              <button
                className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-xl"
                onClick={() => setShowAddWhitelistModal(false)}
              >×</button>
              <h4 className="text-lg font-bold mb-4">添加白名单</h4>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">选择 API Key</label>
                <select
                  className="w-full px-3 py-2 border rounded"
                  value={addWhitelistKeyId ?? ''}
                  onChange={e => setAddWhitelistKeyId(Number(e.target.value))}
                >
                  <option value="">请选择</option>
                  {availableKeys.map((k: any) => (
                    <option key={k.id} value={k.id}>{k.key}（{k.buyer}）</option>
                  ))}
                </select>
              </div>
              <div className="mb-4">
                <label className="block mb-1 text-gray-700">备注</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border rounded"
                  value={addWhitelistRemark}
                  onChange={e => setAddWhitelistRemark(e.target.value)}
                  placeholder="可选，备注信息"
                />
              </div>
              <div className="flex justify-end gap-4">
                <button
                  className="px-4 py-1 rounded bg-gray-200 hover:bg-gray-300"
                  onClick={() => setShowAddWhitelistModal(false)}
                >取消</button>
                <button
                  className="px-4 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                  onClick={handleAddWhitelistModal}
                  disabled={addWhitelistLoading || !addWhitelistKeyId}
                >{addWhitelistLoading ? '添加中...' : '添加'}</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default DashboardPage; 