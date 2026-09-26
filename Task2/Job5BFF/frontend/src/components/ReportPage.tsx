import React, { useEffect, useState } from 'react';

const BFF_URL = process.env.REACT_APP_BFF_URL || 'http://localhost:8000';

type ReportResponse = {
  available: boolean;
  period: { from: string | null; to: string | null };
  user: Record<string, any>;
  telemetry_summary: Record<string, any> | null;
  event_breakdown: Array<{ event_type: string; count: number }>;
  message?: string;
  generated_at: string;
};

const ReportPage: React.FC = () => {
  const [user, setUser] = useState<any>(null);
  const [initialized, setInitialized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  useEffect(() => {
    fetch(`${BFF_URL}/auth/me`, { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : { authenticated: false }))
      .then((data) => setUser(data.user || null))
      .catch(() => setUser(null))
      .finally(() => setInitialized(true));
  }, []);

  const login = () => {
    window.location.href =
      `${BFF_URL}/auth/login?redirect_uri=${encodeURIComponent(window.location.origin)}`;
  };

  const logout = async () => {
    await fetch(`${BFF_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    setUser(null);
    setReport(null);
  };

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError(null);
      setReport(null);

      const params = new URLSearchParams();
      if (fromDate) params.set('from', fromDate);
      if (toDate)   params.set('to', toDate);
      const qs = params.toString();

      const url = `${BFF_URL}/api/reports${qs ? `?${qs}` : ''}`;
      const response = await fetch(url, { credentials: 'include' });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
      }
      setReport(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const resetPeriod = () => { setFromDate(''); setToDate(''); };

  if (!initialized) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-gray-700">Загрузка…</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={login}
          className="px-6 py-3 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Войти
        </button>
      </div>
    );
  }

  const username = user.preferred_username || user.email || user.sub;

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-4xl mx-auto bg-white rounded-lg shadow-md p-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Usage Reports</h1>
          <button
            onClick={logout}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
          >
            Выйти
          </button>
        </div>

        <div className="mb-4 text-sm text-gray-600">
          Вы вошли как <b>{String(username)}</b>
        </div>

        <div className="flex flex-wrap items-end gap-3 mb-6">
          <div>
            <label className="block text-xs text-gray-500 mb-1">С даты</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">По дату</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </div>
          <button
            onClick={resetPeriod}
            className="px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300"
          >
            Сбросить период
          </button>
        </div>

        <button
          onClick={fetchReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Загрузка отчёта…' : 'Получить отчёт'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {report && report.available === false && (
          <div className="mt-4 p-4 bg-yellow-100 text-yellow-800 border border-yellow-300 rounded">
            <div className="font-semibold mb-1">Данные недоступны</div>
            <div>{report.message ?? 'Данные за указанный период недоступны'}</div>
            <div className="text-xs text-yellow-700 mt-2">
              Период запроса: {report.period.from ?? '—'} … {report.period.to ?? '—'}
            </div>
          </div>
        )}

        {report && report.available === true && (
          <div className="mt-6 space-y-6">
            <section>
              <h2 className="text-lg font-semibold mb-2">Профиль</h2>
              <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">
                {JSON.stringify(report.user, null, 2)}
              </pre>
            </section>

            <section>
              <h2 className="text-lg font-semibold mb-2">Метрики телеметрии</h2>
              <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">
                {JSON.stringify(report.telemetry_summary, null, 2)}
              </pre>
            </section>

            <section>
              <h2 className="text-lg font-semibold mb-2">События</h2>
              <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">
                {JSON.stringify(report.event_breakdown, null, 2)}
              </pre>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;