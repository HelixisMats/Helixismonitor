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

function fmt(val, dec = 1) {
  return val != null ? Number(val).toFixed(dec) : '—'
}

// Trapezoid integration: kW × h = kWh
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

function Pipe({ pts, color, flow }) {
  const [offsets, setOffsets] = useState([0, 0.33, 0.66])
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
      <polyline points={d} fill="none" stroke={color} strokeWidth={7}
        strokeLinecap="round" strokeLinejoin="round" opacity={0.2} />
      <polyline points={d} fill="none" stroke={color} strokeWidth={3}
        strokeLinecap="round" strokeLinejoin="round" />
      {(flow ?? 0) > 0.005 && offsets.map((o, i) => {
        const [x, y] = getPoint(pts, o)
        return <circle key={i} cx={x} cy={y} r={3.5} fill={color} opacity={0.95} />
      })}
    </g>
  )
}

function Panel({ x, y, w, h, temp }) {
  const heat = temp != null ? Math.max(0, Math.min(1, (temp-20)/140)) : 0
  const col  = tempColor(temp, 20, 160)
  const slats = 22, sh = h / slats
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={3} fill="#0d0f1c" stroke="#1e2440" strokeWidth={1}/>
      {Array.from({length: slats}, (_, i) => (
        <rect key={i} x={x+3} y={y+i*sh+1.5} width={w-6} height={sh-2.5} rx={1}
          fill={`rgba(160,185,220,${(0.09+heat*0.16+(1-i/slats)*0.05).toFixed(2)})`}
          stroke="rgba(80,100,140,0.1)" strokeWidth={0.3} />
      ))}
      <rect x={x} y={y} width={w} height={h} rx={3} fill="none" stroke="#252a45" strokeWidth={1.5}/>
      <rect x={x} y={y} width={w} height={h} rx={3} fill="none" stroke={col}
        strokeWidth={2} opacity={(0.05+heat*0.65).toFixed(2)}/>
    </g>
  )
}

function Tank({ x, y, w, h, temp }) {
  const heat = temp != null ? Math.max(0, Math.min(1,(temp-10)/90)) : 0
  const col  = tempColor(temp, 10, 100)
  const lvl  = h * 0.72
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill="#0c0e18" stroke="#1e2440" strokeWidth={1}/>
      <rect x={x+2} y={y+h-lvl} width={w-4} height={lvl-2} rx={8} fill={col} opacity={0.18}/>
      <line x1={x+4} x2={x+w-4} y1={y+h-lvl} y2={y+h-lvl}
        stroke={col} strokeWidth={1.5} opacity={0.6} strokeDasharray="5 3"/>
      <rect x={x} y={y} width={w} height={h} rx={10} fill="none" stroke={col}
        strokeWidth={2} opacity={(0.2+heat*0.55).toFixed(2)}/>
    </g>
  )
}

function Consumer({ x, y, w, h }) {
  const fins = 6, sp = (w-16)/(fins-1)
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={6} fill="#0e101e" stroke="#1e2540" strokeWidth={1}/>
      {Array.from({length:fins},(_,i)=>(
        <line key={i} x1={x+8+i*sp} x2={x+8+i*sp} y1={y+8} y2={y+h-8}
          stroke="#2a3560" strokeWidth={3} strokeLinecap="round"/>
      ))}
      <line x1={x+4} x2={x+w-4} y1={y+13} y2={y+13} stroke="#1e2540" strokeWidth={1}/>
      <line x1={x+4} x2={x+w-4} y1={y+h-13} y2={y+h-13} stroke="#1e2540" strokeWidth={1}/>
    </g>
  )
}

function Badge({ x, y, label, val, color, align }) {
  const dir = align === 'right' ? 1 : -1
  const lx  = x + dir * 12
  const anch = align === 'right' ? 'start' : 'end'
  return (
    <g>
      <circle cx={x} cy={y} r={4} fill={color}/>
      <text x={lx} y={y-10} fill="#7788bb" fontSize={10} fontWeight="700"
        fontFamily="'Syne',sans-serif" letterSpacing="0.1em" textAnchor={anch}>{label}</text>
      <text x={lx} y={y+10} fill={color} fontSize={19} fontWeight="800"
        fontFamily="'Syne',sans-serif" textAnchor={anch}>
        {val != null ? fmt(val)+'°' : '—'}
      </text>
    </g>
  )
}

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
      const ts = d.temp_tank?.ts || d.temp_forward?.ts
      setIsLive(ts ? (Date.now() - new Date(ts)) / 60000 < 15 : false)
    }
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const load = async () => {
      const rows = await fetchTodayPower()
      setEnergyToday(integratePower(rows))
    }
    load()
    const id = setInterval(load, 120000)
    return () => clearInterval(id)
  }, [])

  const v = {}
  for (const [k, d] of Object.entries(data)) v[k] = d?.value

  const fwdCol = tempColor(v.temp_forward, 20, 120)
  const retCol = tempColor(v.temp_return,  10, 80)
  const flow   = v.flow ?? 0

  // Pipe routes (SVG 370×410)
  // Forward HOT:  collector(110,252) → down → right → tank top inlet (268,82)
  // Supply  HOT:  tank bottom (340,242) → consumer top (304,288)
  // Return  COOL: consumer bottom (268,346) → left → up → collector (110,252)
  const fwdPts = [[110,252],[110,365],[220,365],[220,82],[268,82]]
  const supPts = [[340,242],[340,288]]
  const retPts = [[268,346],[220,346],[220,385],[110,385],[110,252]]

  const timeStr = lastUpdate
    ? lastUpdate.toLocaleTimeString('sv-SE', {timeStyle:'medium'})
    : '—:—:—'

  return (
    <div style={{
      minHeight:'100dvh', background:'#08090f',
      fontFamily:"'Syne',sans-serif", color:'#e8eaf6',
      display:'flex', flexDirection:'column',
      maxWidth:430, margin:'0 auto',
      paddingBottom:'env(safe-area-inset-bottom)',
    }}>

      {/* Header */}
      <div style={{padding:'14px 18px 12px',borderBottom:'1px solid #13152a',
        display:'flex',alignItems:'center',justifyContent:'space-between',background:'#0b0d18'}}>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <img src="/logo.png" alt="Helixis" height="32"
            onError={e=>{e.target.style.display='none'}} />
          <div>
            <div style={{fontSize:20,fontWeight:800,letterSpacing:'0.05em',color:'#ffffff'}}>HELIXIS</div>
            <div style={{fontSize:9,color:'#3a4270',letterSpacing:'0.2em',marginTop:1}}>LC12 · SOLAR CONCENTRATOR</div>
          </div>
        </div>
        <div style={{textAlign:'right'}}>
          <div style={{display:'flex',alignItems:'center',gap:5,justifyContent:'flex-end'}}>
            <div style={{width:7,height:7,borderRadius:'50%',
              background:isLive?'#00e5a0':'#e55353',
              boxShadow:isLive?'0 0 8px #00e5a0':'0 0 8px #e55353'}}/>
            <span style={{fontSize:11,color:isLive?'#00e5a0':'#e55353',letterSpacing:'0.1em',fontWeight:700}}>
              {isLive?'LIVE':'OFFLINE'}
            </span>
          </div>
          <div style={{fontSize:11,color:'#3a4270',marginTop:3,fontFamily:"'Space Mono',monospace"}}>
            {timeStr}
          </div>
        </div>
      </div>

      {/* Illustration */}
      <div style={{padding:'10px 6px 4px',background:'#08090f'}}>
        <svg viewBox="0 0 370 410" width="100%" style={{display:'block',overflow:'visible'}}>

          <Panel x={10}  y={20} w={100} h={220} temp={v.temp_left_coll}  />
          <Panel x={150} y={20} w={100} h={220} temp={v.temp_right_coll} />

          {/* Mount */}
          <line x1="110" y1="216" x2="94"  y2="246" stroke="#252a45" strokeWidth={2}/>
          <line x1="110" y1="216" x2="126" y2="246" stroke="#252a45" strokeWidth={2}/>
          <line x1="110" y1="216" x2="110" y2="246" stroke="#1e2440" strokeWidth={1.5}/>
          <rect x="101" y="210" width="18" height="9" rx="3" fill="#0e1020"/>
          <rect x="101" y="210" width="18" height="9" rx="3" fill="#4a90d0" opacity="0.65"/>
          <rect x="103" y="247" width="14" height="11" rx="2" fill="#111320" stroke="#1e2440" strokeWidth={1}/>
          <rect x="106" y="258" width="8"  height="16" rx="2" fill="#111320" stroke="#1e2440" strokeWidth={1}/>

          <Tank     x={268} y={55}  w={72} h={188} temp={v.temp_tank} />
          <Consumer x={268} y={288} w={72} h={56}  />

          <text x="304" y="47" textAnchor="middle" fill="#4a5280" fontSize={9}
            letterSpacing="2" fontFamily="'Syne',sans-serif" fontWeight="700">TANK</text>
          <text x="304" y="358" textAnchor="middle" fill="#4a5280" fontSize={9}
            letterSpacing="2" fontFamily="'Syne',sans-serif" fontWeight="700">CONSUMER</text>

          {/* Cover where pipes pass behind tank */}
          <rect x="268" y="234" width="72" height="16" fill="#08090f"/>

          <Pipe pts={retPts} color={retCol} flow={flow}/>
          <Pipe pts={fwdPts} color={fwdCol} flow={flow}/>
          <Pipe pts={supPts} color={fwdCol} flow={flow}/>

          <Badge x={10}  y={52}  label="LEFT"    val={v.temp_left_coll}  color={tempColor(v.temp_left_coll,20,160)}  align="right"/>
          <Badge x={250} y={52}  label="RIGHT"   val={v.temp_right_coll} color={tempColor(v.temp_right_coll,20,160)} align="left"/>
          <Badge x={268} y={148} label="TANK"    val={v.temp_tank}       color={tempColor(v.temp_tank,10,100)}       align="left"/>
          <Badge x={220} y={358} label="FORWARD" val={v.temp_forward}    color={fwdCol} align="right"/>
          <Badge x={220} y={385} label="RETURN"  val={v.temp_return}     color={retCol} align="right"/>
        </svg>
      </div>

      {/* ΔT */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'center',
        gap:8,padding:'2px 14px 10px',background:'#08090f'}}>
        <span style={{fontSize:10,color:'#5060a0',letterSpacing:'0.15em',fontWeight:700}}>TEMP DIFFERENTIAL</span>
        <span style={{fontFamily:"'Space Mono',monospace",fontSize:20,fontWeight:700,color:'#ffffff'}}>
          {fmt(v.temp_difference,1)}
        </span>
        <span style={{fontSize:10,color:'#5060a0'}}>°C</span>
      </div>

      {/* Stats */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:1,background:'#13152a',borderTop:'1px solid #13152a'}}>
        {[
          {label:'POWER',    val:v.power,      dec:2, unit:'kW',   color:'#e87d4a'},
          {label:'FLOW',     val:v.flow,       dec:3, unit:'m³/h', color:'#4a9ee8'},
          {label:'IRRAD.',   val:v.irradiance, dec:0, unit:'W/m²', color:'#e8c84a'},
          {label:'PRESSURE', val:v.pressure,   dec:2, unit:'bar',
            color:(v.pressure??0)>=5?'#e85353':'#507090'},
        ].map(s=>(
          <div key={s.label} style={{background:'#08090f',padding:'12px 6px',textAlign:'center'}}>
            <div style={{fontSize:9,color:'#5060a0',letterSpacing:'0.15em',marginBottom:4,fontWeight:700}}>{s.label}</div>
            <div style={{fontSize:18,fontWeight:700,color:s.color,lineHeight:1,fontFamily:"'Space Mono',monospace"}}>
              {s.val!=null?Number(s.val).toFixed(s.dec):'—'}
            </div>
            <div style={{fontSize:9,color:'#5060a0',marginTop:3}}>{s.unit}</div>
          </div>
        ))}
      </div>

      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:1,background:'#13152a'}}>
        <div style={{background:'#08090f',padding:'11px 14px',display:'flex',alignItems:'center',justifyContent:'space-between'}}>
          <span style={{fontSize:10,color:'#5060a0',letterSpacing:'0.12em',fontWeight:700}}>ENERGY TODAY</span>
          <span>
            <span style={{fontFamily:"'Space Mono',monospace",fontSize:16,fontWeight:700,color:'#00e5a0'}}>
              {energyToday!=null?energyToday.toFixed(3):'—'}
            </span>
            <span style={{fontSize:9,color:'#5060a0',marginLeft:4}}>kWh</span>
          </span>
        </div>
        <div style={{background:'#08090f',padding:'11px 14px',display:'flex',alignItems:'center',justifyContent:'space-between'}}>
          <span style={{fontSize:10,color:'#5060a0',letterSpacing:'0.12em',fontWeight:700}}>WIND</span>
          <span>
            <span style={{fontFamily:"'Space Mono',monospace",fontSize:16,fontWeight:700,color:'#e8eaf6'}}>
              {v.wind!=null?Number(v.wind).toFixed(2):'—'}
            </span>
            <span style={{fontSize:9,color:'#5060a0',marginLeft:4}}>m/s</span>
          </span>
        </div>
      </div>

      <div style={{padding:'8px',fontSize:8,color:'#181d30',letterSpacing:'0.1em',textAlign:'center'}}>
        HELIXIS LC12 · 12.35 m² · 9.2 kW PEAK · 380 KG
      </div>
    </div>
  )
}
