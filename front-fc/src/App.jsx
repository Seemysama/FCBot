import React, { useState, useEffect, useRef } from 'react';
import { Activity, Server, ShieldAlert, Zap, Database, Terminal, Play, Pause, Settings, Globe, Lock, Search } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip } from 'recharts';

const INITIAL_WORKERS = [
  { id: 'W-01', status: 'idle', proxy: '192.168.1.101', type: 'Sniper (Go)', rtt: 45 },
  { id: 'W-02', status: 'active', proxy: '45.32.11.22', type: 'Bidder (Py)', rtt: 112 },
  { id: 'W-03', status: 'cooldown', proxy: '88.12.44.12', type: 'Sniper (Go)', rtt: 55 },
  { id: 'W-04', status: 'banned', proxy: '102.11.23.99', type: 'Bidder (Py)', rtt: 0 },
];

const TARGET_PLAYERS = [
  { id: 1, name: 'K. Mbappé', rating: 91, buyPrice: 1500000, profit: 75000, volatility: 'High' },
  { id: 2, name: 'V. Vinícius Jr', rating: 89, buyPrice: 900000, profit: 31000, volatility: 'Med' },
  { id: 3, name: 'J. Bellingham', rating: 88, buyPrice: 450000, profit: 15500, volatility: 'Low' },
];

const generateLog = (counter) => {
  const actions = [
    { type: 'INFO', msg: '[TLS-Fingerprint] JA3 signature matched: 771,4865-4866... (iOS 17)' },
    { type: 'SUCCESS', msg: '[SNIPE] 200 OK | POST /ut/game/fc26/transfermarket | 42ms' },
    { type: 'WARN', msg: '[Heuristic] Mouse movement entropy too low. Injecting noise.' },
    { type: 'INFO', msg: '[Proxy] Rotating IP due to HTTP 429.' },
    { type: 'ERROR', msg: '[Auth] Token refresh failed for W-04. Kill switch.' },
    { type: 'INFO', msg: '[Market] Parsing 50 items. Found 2 targets.' },
  ];
  const randomAction = actions[Math.floor(Math.random() * actions.length)];
  return { id: counter, time: new Date().toLocaleTimeString('fr-FR'), ...randomAction };
};

export default function App() {
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState([]);
  const [marketData, setMarketData] = useState([]);
  const [workers, setWorkers] = useState(INITIAL_WORKERS);
  const [stats, setStats] = useState({ totalProfit: 1245000, rpm: 0, activeProxies: 12 });
  const logEndRef = useRef(null);

  useEffect(() => {
    let interval;
    if (isRunning) {
      interval = setInterval(() => {
        setMarketData(prev => {
          const lastPrice = prev.length > 0 ? prev[prev.length - 1].price : 1500000;
          const newPrice = Math.floor(lastPrice + (Math.random() - 0.5) * 5000);
          return [...prev.slice(-19), { time: new Date().toLocaleTimeString(), price: newPrice }];
        });
        setLogs(prev => [...prev.slice(-15), generateLog(Date.now())]);
        setWorkers(prev => prev.map(w => w.status === 'banned' ? w : { ...w, rtt: Math.max(10, w.rtt + Math.floor(Math.random() * 20) - 10) }));
        setStats(prev => ({
          ...prev,
          totalProfit: prev.totalProfit + (Math.random() > 0.8 ? 1500 : 0),
          rpm: Math.floor(Math.random() * 2000) + 3000
        }));
      }, 800);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#020617', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif' }}>
      {/* HEADER */}
      <header style={{ borderBottom: '1px solid #1e293b', backgroundColor: 'rgba(15,23,42,0.5)', padding: '0 16px', height: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Database style={{ width: 24, height: 24, color: '#10b981' }} />
          <span style={{ fontWeight: 'bold', fontSize: 18 }}>FUT<span style={{ color: '#10b981' }}>QUANT</span>.SYS</span>
          <span style={{ marginLeft: 8, fontSize: 12, backgroundColor: '#1e293b', padding: '2px 8px', borderRadius: 4, color: '#94a3b8', border: '1px solid #334155' }}>v4.2.0-Alpha</span>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <button 
            onClick={() => setIsRunning(!isRunning)}
            style={{ 
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 6, fontWeight: 'bold', fontSize: 14, cursor: 'pointer', transition: 'all 0.2s',
              backgroundColor: isRunning ? 'rgba(239,68,68,0.1)' : 'rgba(16,185,129,0.1)',
              color: isRunning ? '#ef4444' : '#10b981',
              border: isRunning ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(16,185,129,0.5)'
            }}
          >
            {isRunning ? <><Pause size={16} /> ARRÊT D'URGENCE</> : <><Play size={16} /> INITIALISER LE CLUSTER</>}
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontFamily: 'monospace', color: '#64748b', backgroundColor: '#0f172a', padding: '4px 12px', borderRadius: 4, border: '1px solid #1e293b' }}>
            <div style={{ width: 8, height: 8, backgroundColor: '#10b981', borderRadius: '50%', animation: 'pulse 2s infinite' }}></div>
            SOCKET: CONNECTED
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1280, margin: '0 auto', padding: 16, display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 16, marginTop: 16 }}>
        
        {/* KPI ROW */}
        <div style={{ gridColumn: 'span 12', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 8 }}>
          {[
            { title: 'Profit Net (24h)', value: `${stats.totalProfit.toLocaleString()} CR`, sub: '+12.4% vs target', color: '#10b981', Icon: Activity },
            { title: 'Requêtes / Min', value: stats.rpm, sub: 'Load Balancing: Optimal', color: '#3b82f6', Icon: Zap },
            { title: 'Proxies Rotatifs', value: stats.activeProxies, sub: '3 Blacklisted', color: '#a855f7', Icon: Globe },
            { title: 'OpSec Status', value: 'LOW RISK', sub: 'TLS Fingerprint: Clean', color: '#10b981', Icon: ShieldAlert },
          ].map((card, i) => (
            <div key={i} style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', padding: 16, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ color: '#94a3b8', fontSize: 12, textTransform: 'uppercase', fontWeight: 'bold', letterSpacing: 1 }}>{card.title}</p>
                <p style={{ fontSize: 24, fontFamily: 'monospace', color: 'white', marginTop: 4 }}>{card.value}</p>
                <p style={{ fontSize: 12, marginTop: 4, color: card.color }}>{card.sub}</p>
              </div>
              <div style={{ padding: 12, borderRadius: '50%', backgroundColor: `${card.color}20` }}>
                <card.Icon style={{ width: 24, height: 24, color: card.color }} />
              </div>
            </div>
          ))}
        </div>

        {/* LEFT COLUMN */}
        <div style={{ gridColumn: 'span 3', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 16 }}>
            <h3 style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Server size={14} /> Worker Nodes
            </h3>
            {workers.map(w => (
              <div key={w.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 8px', borderBottom: '1px solid #1e293b' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: w.status === 'active' ? '#10b981' : w.status === 'banned' ? '#dc2626' : '#f59e0b' }} />
                  <div>
                    <p style={{ fontSize: 14, fontWeight: 'bold', color: '#e2e8f0' }}>{w.id}</p>
                    <p style={{ fontSize: 12, color: '#64748b', fontFamily: 'monospace' }}>{w.type}</p>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <p style={{ fontSize: 12, fontFamily: 'monospace', color: '#64748b' }}>{w.proxy}</p>
                  <p style={{ fontSize: 12, fontWeight: 'bold', color: w.rtt < 50 ? '#10b981' : '#f59e0b' }}>RTT: {w.rtt}ms</p>
                </div>
              </div>
            ))}
            <button style={{ width: '100%', marginTop: 16, padding: 8, fontSize: 12, fontWeight: 'bold', backgroundColor: '#1e293b', color: '#94a3b8', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
              + DÉPLOYER INSTANCE (DOCKER)
            </button>
          </div>

          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 16 }}>
            <h3 style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Settings size={14} /> Paramètres de Sniping
            </h3>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#64748b', display: 'block', marginBottom: 4 }}>Seuil de profit min (Kelly)</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="range" style={{ flex: 1 }} />
                <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#10b981' }}>5.2%</span>
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#64748b', display: 'block', marginBottom: 4 }}>Max RTT Tolérance</label>
              <div style={{ backgroundColor: '#1e293b', padding: '4px 8px', borderRadius: 4, fontSize: 12, fontFamily: 'monospace', color: '#cbd5e1' }}>150ms</div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: '#64748b' }}>Mode Humanisation</span>
              <span style={{ color: '#10b981', fontWeight: 'bold' }}>ACTIF (Poisson)</span>
            </div>
          </div>
        </div>

        {/* MIDDLE COLUMN */}
        <div style={{ gridColumn: 'span 6', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* CHART */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 16, height: 256 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Activity size={14} /> Analyse de Marché (Index Top 100)
              </h3>
              <span style={{ fontSize: 10, padding: '2px 8px', backgroundColor: 'rgba(16,185,129,0.2)', color: '#10b981', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 4 }}>BULLISH</span>
            </div>
            <ResponsiveContainer width="100%" height="80%">
              <AreaChart data={marketData}>
                <defs>
                  <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis domain={['auto', 'auto']} hide />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: 12 }} itemStyle={{ color: '#10b981' }} />
                <Area type="monotone" dataKey="price" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorPrice)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* TERMINAL */}
          <div style={{ backgroundColor: '#000', border: '1px solid #1e293b', borderRadius: 8, padding: 16, height: 320, fontFamily: 'monospace', fontSize: 12, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #111' }}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: 8 }}><Terminal size={12} /> SYSTEM LOGS</span>
              <div style={{ display: 'flex', gap: 4 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: 'rgba(239,68,68,0.2)' }}></div>
                <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: 'rgba(234,179,8,0.2)' }}></div>
                <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: 'rgba(34,197,94,0.2)' }}></div>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {logs.length === 0 && <span style={{ color: '#475569', fontStyle: 'italic' }}>En attente de l'initialisation du cluster...</span>}
              {logs.map((log) => (
                <div key={log.id} style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
                  <span style={{ color: '#475569' }}>[{log.time}]</span>
                  <span style={{ color: log.type === 'ERROR' ? '#ef4444' : log.type === 'SUCCESS' ? '#10b981' : log.type === 'WARN' ? '#f59e0b' : '#60a5fa' }}>{log.type}</span>
                  <span style={{ color: '#cbd5e1' }}>{log.msg}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div style={{ gridColumn: 'span 3' }}>
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: 16, height: '100%' }}>
            <h3 style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Search size={14} /> Cibles Prioritaires
            </h3>
            {TARGET_PLAYERS.map(player => (
              <div key={player.id} style={{ backgroundColor: 'rgba(2,6,23,0.5)', padding: 12, borderRadius: 6, border: '1px solid rgba(30,41,59,0.5)', marginBottom: 12, cursor: 'pointer' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div>
                    <span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>Rating {player.rating}</span>
                    <span style={{ fontWeight: 'bold', color: '#e2e8f0' }}>{player.name}</span>
                  </div>
                  <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, backgroundColor: player.volatility === 'High' ? 'rgba(239,68,68,0.2)' : 'rgba(59,130,246,0.2)', color: player.volatility === 'High' ? '#ef4444' : '#3b82f6' }}>
                    {player.volatility} VOL
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontFamily: 'monospace' }}>
                  <span style={{ color: '#64748b' }}>Buy: {(player.buyPrice/1000).toFixed(0)}k</span>
                  <span style={{ color: '#10b981' }}>+{player.profit.toLocaleString()}</span>
                </div>
                <div style={{ marginTop: 8, width: '100%', height: 4, backgroundColor: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ width: '70%', height: '100%', backgroundColor: '#10b981' }}></div>
                </div>
              </div>
            ))}
            
            <div style={{ padding: 12, border: '1px dashed #334155', borderRadius: 6, textAlign: 'center', cursor: 'pointer', marginTop: 8 }}>
              <span style={{ fontSize: 12, color: '#64748b' }}>+ Importer CSV / Futbin URL</span>
            </div>

            <div style={{ marginTop: 24, paddingTop: 24, borderTop: '1px solid #1e293b' }}>
              <h3 style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Lock size={14} /> Bypass Modules
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ backgroundColor: '#020617', padding: 8, borderRadius: 4, textAlign: 'center', border: '1px solid #1e293b' }}>
                  <span style={{ display: 'block', fontSize: 10, color: '#64748b' }}>Arkose Solver</span>
                  <span style={{ fontSize: 12, fontWeight: 'bold', color: '#10b981' }}>READY</span>
                </div>
                <div style={{ backgroundColor: '#020617', padding: 8, borderRadius: 4, textAlign: 'center', border: '1px solid #1e293b' }}>
                  <span style={{ display: 'block', fontSize: 10, color: '#64748b' }}>TLS Spoofing</span>
                  <span style={{ fontSize: 12, fontWeight: 'bold', color: '#10b981' }}>ACTIVE</span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </main>
      <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
    </div>
  );
}
