"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  // 页面加载时如已登录，自动跳转 dashboard
  useEffect(() => {
    if (typeof window !== "undefined") {
      const isLogin = document.cookie.split('; ').find(row => row.startsWith('isLogin='));
      if (isLogin && isLogin.split('=')[1] === 'true') {
        router.replace("/dashboard");
      }
    }
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    // 请求后端接口校验
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const result = await res.json();
    if (res.ok && result.success) {
      // 登录成功，设置 cookie 并跳转 dashboard
      const expires = new Date(Date.now() + 24 * 60 * 60 * 1000).toUTCString();
      document.cookie = `isLogin=true; path=/; expires=${expires}`;
      router.push("/dashboard");
    } else {
      setError(result.error || "登录失败");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100">
      <form
        onSubmit={handleLogin}
        className="bg-white p-8 rounded shadow-md w-full max-w-sm"
      >
        <h2 className="text-2xl font-bold mb-6 text-center">后台登录</h2>
        <div className="mb-4">
          <label className="block mb-1 text-gray-700">账号</label>
          <input
            type="text"
            className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="请输入账号"
            autoComplete="username"
          />
        </div>
        <div className="mb-4">
          <label className="block mb-1 text-gray-700">密码</label>
          <input
            type="password"
            className="w-full px-3 py-2 border rounded focus:outline-none focus:ring focus:border-blue-300"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="请输入密码"
            autoComplete="current-password"
          />
        </div>
        {error && <div className="mb-4 text-red-500 text-sm">{error}</div>}
        <button
          type="submit"
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition"
        >
          登录
        </button>
      </form>
    </div>
  );
} 