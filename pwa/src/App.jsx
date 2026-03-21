import { useState, useEffect } from 'react'
import { fetchLatestReadings, fetchTodayPower } from './supabase.js'

function tempColor(val, mn, mx) {
  if (val == null) return '#3a4060'
  const t = Math.max(0, Math.min(1, (val - mn) / (mx - mn)))
  if (t < 0.5) {
    const s = t * 2
    return `rgb(${Math.round(40+s*146)},${Math.round(100-s*5)},${Math.round(200-s*200)})`
  }
  const s = (t - 0.5) * 2
  return `rgb(${Math.round(186+s*24)},${Math.round(95-s*60)},0)`
}

function fmt(val, dec = 1) { return val != null ? Number(val).toFixed(dec) : '—' }

function integratePower(rows) {
  if (!rows || rows.length < 2) return null
  let energy = 0
  for (let i = 1; i < rows.length; i++) {
    const dt = (new Date(rows[i].created_at) - new Date(rows[i-1].created_at)) / 3600000
    energy += ((rows[i].value + rows[i-1].value) / 2) * dt
  }
  return Math.max(0, energy)
}

function getPoint(pts, t) {
  const lens = []; let total = 0
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1])
    lens.push(d); total += d
  }
  let rem = t * total
  for (let i = 0; i < lens.length; i++) {
    if (rem <= lens[i]) {
      const f = rem / lens[i]
      return [pts[i][0]+f*(pts[i+1][0]-pts[i][0]), pts[i][1]+f*(pts[i+1][1]-pts[i][1])]
    }
    rem -= lens[i]
  }
  return pts[pts.length-1]
}

function Pipe({ pts, color, flow, id }) {
  const [offsets, setOffsets] = useState([0, 0.35, 0.68])
  const speed = Math.max(0.001, (flow ?? 0) * 0.005)
  useEffect(() => {
    let frame
    const tick = () => {
      setOffsets(prev => prev.map(o => (o + speed) % 1))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [speed])
  const d = pts.map(p => p.join(',')).join(' ')
  return (
    <g>
      <polyline points={d} fill="none" stroke={color} strokeWidth={8}
        strokeLinecap="round" strokeLinejoin="round" opacity={0.18} />
      <polyline points={d} fill="none" stroke={color} strokeWidth={3.5}
        strokeLinecap="round" strokeLinejoin="round" />
      {(flow ?? 0) > 0.005 && offsets.map((o, i) => {
        const [x, y] = getPoint(pts, o)
        return <circle key={i} cx={x} cy={y} r={4} fill={color} opacity={0.9} />
      })}
    </g>
  )
}

function Panel({ x, y, w, h, temp }) {
  const heat = temp != null ? Math.max(0, Math.min(1, (temp-20)/140)) : 0
  const col  = tempColor(temp, 20, 160)
  const slats = 24, sh = h / slats
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={3} fill="#0d0f1c" stroke="#1e2440" strokeWidth={1}/>
      {Array.from({length:slats}, (_, i) => (
        <rect key={i} x={x+3} y={y+i*sh+1.5} width={w-6} height={sh-2.5} rx={1}
          fill={`rgba(160,185,220,${(0.08+heat*0.17+(1-i/slats)*0.04).toFixed(2)})`}
          stroke="rgba(80,100,140,0.1)" strokeWidth={0.3} />
      ))}
      <rect x={x} y={y} width={w} height={h} rx={3} fill="none" stroke="#252a45" strokeWidth={1.5}/>
      <rect x={x} y={y} width={w} height={h} rx={3} fill="none" stroke={col}
        strokeWidth={2} opacity={(0.05+heat*0.65).toFixed(2)}/>
    </g>
  )
}

function Tank({ x, y, w, h, temp }) {
  const heat = temp != null ? Math.max(0, Math.min(1, (temp-10)/90)) : 0
  const col  = tempColor(temp, 10, 100)
  const lvl  = h * 0.7
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="#0c0e18" stroke="#1e2440" strokeWidth={1}/>
      <rect x={x+2} y={y+h-lvl} width={w-4} height={lvl-2} rx={6} fill={col} opacity={0.2}/>
      <line x1={x+6} x2={x+w-6} y1={y+h-lvl} y2={y+h-lvl}
        stroke={col} strokeWidth={1.5} opacity={0.7} strokeDasharray="5 3"/>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="none" stroke={col}
        strokeWidth={2} opacity={(0.2+heat*0.55).toFixed(2)}/>
    </g>
  )
}

function Consumer({ x, y, w, h }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill="#0e101e" stroke="#1e2540" strokeWidth={1}/>
      <path d={`M${x+18} ${y+16} Q${x+w/2} ${y+16} ${x+w/2} ${y+32} Q${x+w/2} ${y+48} ${x+18} ${y+48} Q${x+w/2} ${y+48} ${x+w/2} ${y+64} Q${x+w/2} ${y+80} ${x+18} ${y+80}`}
        fill="none" stroke="#2a3560" strokeWidth={3} strokeLinecap="round"/>
    </g>
  )
}

const LABEL = { fontSize: 9, fontWeight: 700, fontFamily: "'Syne',sans-serif", letterSpacing: '0.12em', fill: '#5060a0' }
const VAL   = { fontFamily: "'Syne',sans-serif", fontWeight: 800 }
const MONO  = { fontFamily: "'Space Mono',monospace", fontWeight: 700 }

export default function App() {
  const [data,        setData]        = useState({})
  const [energyToday, setEnergyToday] = useState(null)
  const [lastUpdate,  setLastUpdate]  = useState(null)
  const [isLive,      setIsLive]      = useState(false)

  useEffect(() => {
    const load = async () => {
      const d = await fetchLatestReadings()
      setData(d)
      setLastUpdate(new Date())
      const ts = d.temp_forward?.ts || d.temp_tank?.ts
      setIsLive(ts ? (Date.now() - new Date(ts)) / 60000 < 15 : false)
    }
    load(); const id = setInterval(load, 30000); return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const load = async () => {
      const rows = await fetchTodayPower()
      setEnergyToday(integratePower(rows))
    }
    load(); const id = setInterval(load, 120000); return () => clearInterval(id)
  }, [])

  const v = {}
  for (const [k, d] of Object.entries(data)) v[k] = d?.value

  const fwdCol = tempColor(v.temp_forward, 20, 120)
  const retCol = tempColor(v.temp_return,  10, 80)
  const flow   = v.flow ?? 0

  // SVG 370×640, cx=185
  // Left panel:  x=30  y=64  w=120 h=230  cx=90
  // Right panel: x=220 y=64  w=120 h=230  cx=280
  // Receiver:    x=173 y=158 w=24  (cx=185)
  // Forward pipe exits x=197, return x=173
  // Both go to y=310, fwd turns right to tank top (290,310→290,360)
  //                   ret turns left to consumer top (80,310→80,360)
  // Bottom: consumer bottom (80,462) → 80,502 → 290,502 → tank bottom (290,462)

  const fwdPts = [[197,168],[197,310],[290,310],[290,360]]
  const retPts = [[173,168],[173,310],[80, 310],[80, 360]]
  const botPts = [[80, 462],[80, 502],[290,502],[290,462]]

  const timeStr = lastUpdate
    ? lastUpdate.toLocaleTimeString('sv-SE', {timeStyle:'medium'})
    : '—:—:—'

  return (
    <div style={{
      minHeight: '100dvh', background: '#08090f',
      fontFamily: "'Syne',sans-serif", color: '#e8eaf6',
      display: 'flex', flexDirection: 'column',
      maxWidth: 430, margin: '0 auto',
      paddingBottom: 'env(safe-area-inset-bottom)',
    }}>

      {/* Header */}
      <div style={{padding:'12px 16px 10px',borderBottom:'1px solid #13152a',
        display:'flex',alignItems:'center',justifyContent:'space-between',background:'#0b0d18'}}>
        <div style={{display:'flex',alignItems:'center',gap:9}}>
          <img src="/logo.png" alt="Helixis" height="32"
            onError={e=>{e.target.style.display='none'}} style={{display:'block'}} />
          <div>
            <div style={{fontSize:19,fontWeight:800,letterSpacing:'0.05em',color:'#fff'}}>HELIXIS</div>
            <div style={{fontSize:8,color:'#3a4270',letterSpacing:'0.18em',marginTop:1}}>LC12 · SOLAR CONCENTRATOR</div>
          </div>
        </div>
        <div style={{textAlign:'right'}}>
          <div style={{display:'flex',alignItems:'center',gap:4,justifyContent:'flex-end'}}>
            <div style={{width:7,height:7,borderRadius:'50%',
              background:isLive?'#00e5a0':'#e55353',
              boxShadow:isLive?'0 0 8px #00e5a0':'0 0 8px #e55353'}}/>
            <span style={{fontSize:10,color:isLive?'#00e5a0':'#e55353',letterSpacing:'0.1em',fontWeight:700}}>
              {isLive?'LIVE':'OFFLINE'}
            </span>
          </div>
          <div style={{fontSize:10,color:'#3a4270',marginTop:2,fontFamily:"'Space Mono',monospace"}}>
            {timeStr}
          </div>
        </div>
      </div>

      {/* SVG */}
      <div style={{padding:'8px 6px 0',background:'#08090f',flex:1}}>
      <svg viewBox="0 0 370 640" width="100%" style={{display:'block'}}>

        {/* TOP METRICS */}
        <text x="90"  y="20" textAnchor="middle" {...LABEL}>WIND</text>
        <text x="90"  y="44" textAnchor="middle" fontSize={24} {...VAL} fill="#e8eaf6">{fmt(v.wind,1)}</text>
        <text x="90"  y="58" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">m/s</text>

        <text x="280" y="20" textAnchor="middle" {...LABEL}>IRRADIATION</text>
        <text x="280" y="44" textAnchor="middle" fontSize={24} {...VAL} fill="#e8c84a">{fmt(v.irradiance,0)}</text>
        <text x="280" y="58" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">W/m²</text>

        {/* COLLECTORS */}
        <Panel x={30}  y={64} w={120} h={230} temp={v.temp_left_coll}  />
        <Panel x={220} y={64} w={120} h={230} temp={v.temp_right_coll} />

        <text x="90"  y="79" textAnchor="middle" {...LABEL}>LEFT COLLECTOR</text>
        <text x="90"  y="101" textAnchor="middle" fontSize={22} {...VAL} fill={tempColor(v.temp_left_coll,20,160)}>
          {fmt(v.temp_left_coll)}°
        </text>
        <text x="280" y="79"  textAnchor="middle" {...LABEL}>RIGHT COLLECTOR</text>
        <text x="280" y="101" textAnchor="middle" fontSize={22} {...VAL} fill={tempColor(v.temp_right_coll,20,160)}>
          {fmt(v.temp_right_coll)}°
        </text>

        {/* CENTRAL MOUNT */}
        <rect x="173" y="158" width="24" height="10" rx="4" fill="#0e1020"/>
        <rect x="173" y="158" width="24" height="10" rx="4" fill={fwdCol} opacity="0.8"/>
        <line x1="185" y1="168" x2="168" y2="240" stroke="#1e2845" strokeWidth={2.5}/>
        <line x1="185" y1="168" x2="202" y2="240" stroke="#1e2845" strokeWidth={2.5}/>
        <line x1="185" y1="168" x2="185" y2="240" stroke="#252a45" strokeWidth={1.5}/>
        <rect x="174" y="238" width="22" height="14" rx="3" fill="#111320" stroke="#1e2845" strokeWidth={1}/>
        <rect x="180" y="252" width="10" height="22" rx="3" fill="#111320" stroke="#1e2845" strokeWidth={1}/>

        {/* TANK */}
        <Tank x={240} y={360} w={100} h={102} temp={v.temp_tank} />
        <text x="290" y="354" textAnchor="middle" {...LABEL}>STORAGE TANK</text>
        <text x="290" y="478" textAnchor="middle" fontSize={19} {...VAL} fill={tempColor(v.temp_tank,10,100)}>
          {fmt(v.temp_tank)}°
        </text>

        {/* CONSUMER */}
        <Consumer x={30} y={360} w={100} h={102} />
        <text x="80" y="478" textAnchor="middle" {...LABEL}>CONSUMER</text>

        {/* Cover crossing */}
        <rect x="165" y="297" width="38" height="26" fill="#08090f"/>

        {/* PIPES */}
        <Pipe pts={retPts} color={retCol} flow={flow} />
        <Pipe pts={fwdPts} color={fwdCol} flow={flow} />
        <Pipe pts={botPts} color={retCol} flow={flow} />

        {/* Redraw forward on top of cover */}
        <polyline points="197,168 197,320" fill="none" stroke={fwdCol} strokeWidth={3.5} strokeLinecap="round"/>

        {/* PIPE LABELS */}
        <text x="126" y="291" textAnchor="middle" {...LABEL}>RETURN</text>
        <text x="126" y="311" textAnchor="middle" fontSize={19} {...VAL} fill={retCol}>
          {fmt(v.temp_return)}°
        </text>

        <text x="185" y="338" textAnchor="middle" {...LABEL}>ΔT</text>
        <text x="185" y="358" textAnchor="middle" fontSize={19} {...VAL} fill="#ffffff">
          {fmt(v.temp_difference)}°
        </text>

        <text x="244" y="291" textAnchor="middle" {...LABEL}>FORWARD</text>
        <text x="244" y="311" textAnchor="middle" fontSize={19} {...VAL} fill={fwdCol}>
          {fmt(v.temp_forward)}°
        </text>

        {/* BOTTOM METRICS */}
        <line x1="20" y1="496" x2="350" y2="496" stroke="#13152a" strokeWidth={1}/>

        <text x="90"  y="516" textAnchor="middle" {...LABEL}>ENERGY TODAY</text>
        <text x="90"  y="540" textAnchor="middle" fontSize={22} {...MONO} fill="#00e5a0">
          {energyToday!=null?energyToday.toFixed(3):'—'}
        </text>
        <text x="90"  y="554" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">kWh</text>

        <text x="185" y="516" textAnchor="middle" {...LABEL}>POWER · FLOW</text>
        <text x="152" y="540" textAnchor="middle" fontSize={22} {...MONO} fill="#e87d4a">
          {fmt(v.power,2)}
        </text>
        <text x="152" y="554" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">kW</text>
        <text x="222" y="540" textAnchor="middle" fontSize={22} {...MONO} fill="#4a9ee8">
          {fmt(v.flow,3)}
        </text>
        <text x="222" y="554" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">m³/h</text>

        <text x="290" y="516" textAnchor="middle" {...LABEL}>PRESSURE</text>
        <text x="290" y="540" textAnchor="middle" fontSize={22} {...MONO}
          fill={(v.pressure??0)>=5?'#e85353':'#507090'}>
          {fmt(v.pressure,2)}
        </text>
        <text x="290" y="554" textAnchor="middle" fontSize={9} fontFamily="'Syne',sans-serif" fill="#5060a0">bar</text>

        <text x="185" y="578" textAnchor="middle" fontSize={8}
          fontFamily="'Syne',sans-serif" fill="#1e2440" letterSpacing="1">
          HELIXIS LC12 · 12.35 m² · 9.2 kW PEAK · 380 KG
        </text>
      </svg>
      </div>
    </div>
  )
}
