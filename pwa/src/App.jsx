import { useState, useEffect } from 'react'
import { fetchLatestReadings } from './supabase.js'

function tempColor(val, mn, mx) {
  if (val == null) return '#3a4060'
  const t = Math.max(0, Math.min(1, (val - mn) / (mx - mn)))
  if (t < 0.5) {
    const s = t * 2
    return `rgb(${Math.round(40 + s * 146)},${Math.round(100 - s * 5)},${Math.round(200 - s * 200)})`
  }
  const s = (t - 0.5) * 2
  return `rgb(${Math.round(186 + s * 24)},${Math.round(95 - s * 60)},0)`
}

function fmt(val, dec = 1) {
  return val != null ? val.toFixed(dec) : '—'
}

function FlowParticles({ path, color, speed = 5, count = 4 }) {
  const [offsets, setOffsets] = useState(() =>
    Array.from({ length: count }, (_, i) => i / count)
  )
  useEffect(() => {
    let frame
    const tick = () => {
      setOffsets(prev => prev.map(o => (o + 0.0025 * speed) % 1))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [speed])

  function getPoint(pts, t) {
    const lengths = []
    let total = 0
    for (let i = 1; i < pts.length; i++) {
      const d = Math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1])
      lengths.push(d); total += d
    }
    let rem = t * total
    for (let i = 0; i < lengths.length; i++) {
      if (rem <= lengths[i]) {
        const f = rem / lengths[i]
        return [pts[i][0] + f * (pts[i+1][0] - pts[i][0]),
                pts[i][1] + f * (pts[i+1][1] - pts[i][1])]
      }
      rem -= lengths[i]
    }
    return pts[pts.length - 1]
  }

  return <>
    {offsets.map((o, i) => {
      const [x, y] = getPoint(path, o)
      return <circle key={i} cx={x} cy={y} r={3.5}
        fill={color} opacity={0.95}
        style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
    })}
  </>
}

function Badge({ x, y, label, value, color, align = 'right' }) {
  const dir = align === 'right' ? 1 : -1
  return (
    <g>
      <circle cx={x} cy={y} r={4.5} fill={color}
        style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
      <line x1={x + dir * 10} y1={y} x2={x + dir * 26} y2={y}
        stroke={color} strokeWidth={1} opacity={0.4} />
      <text x={x + dir * 32} y={y - 8}
        textAnchor={align === 'right' ? 'start' : 'end'}
        fill="#5a6490" fontSize={10} letterSpacing="0.1em"
        fontFamily="'Space Mono', monospace">{label}</text>
      <text x={x + dir * 32} y={y + 9}
        textAnchor={align === 'right' ? 'start' : 'end'}
        fill={color} fontSize={16} fontWeight="700"
        fontFamily="'Space Mono', monospace">
        {value != null ? `${fmt(value)}°` : '—'}
      </text>
    </g>
  )
}

// Parabolic trough collector — front view
// Each wing curves inward toward the central receiver tube
function ParabolicCollector({ cx, topY, wingW, wingH, temperature, side }) {
  const heat = temperature != null ? Math.max(0, Math.min(1, (temperature - 20) / 140)) : 0
  const col  = tempColor(temperature, 20, 160)
  const mirrorCount = 20
  const strips = []

  // side: 'left' wing goes cx → cx-wingW, 'right' wing goes cx → cx+wingW
  const dir = side === 'left' ? -1 : 1

  for (let i = 0; i < mirrorCount; i++) {
    const t0 = i / mirrorCount
    const t1 = (i + 0.88) / mirrorCount

    // x: linear from centre outward
    const x0 = cx + dir * t0 * wingW
    const x1 = cx + dir * t1 * wingW

    // y: parabolic — inner strips near top (receiver), outer strips lower
    const y0 = topY + t0 * t0 * wingH
    const y1 = topY + t1 * t1 * wingH

    // Normal direction (perpendicular to strip surface, toward receiver glow)
    const dx = x1 - x0, dy = y1 - y0
    const len = Math.hypot(dx, dy) || 1
    const nx = -dy / len, ny = dx / len
    const thick = 3.5
    // tilt normal inward toward focal line
    const tiltX = nx * thick - dir * ny * thick * 0.3
    const tiltY = ny * thick + Math.abs(nx) * thick * 0.2

    const brightness = 0.2 + (1 - t0) * 0.55 + heat * 0.2

    strips.push(
      <polygon key={i}
        points={[
          `${x0},${y0}`,
          `${x1},${y1}`,
          `${x1 + tiltX},${y1 + tiltY}`,
          `${x0 + tiltX},${y0 + tiltY}`,
        ].join(' ')}
        fill={`rgba(175,200,230,${brightness})`}
        stroke="rgba(80,100,140,0.25)"
        strokeWidth={0.4}
      />
    )
  }

  // Outer frame curve
  const outerPts = Array.from({ length: 24 }, (_, i) => {
    const t = i / 23
    const x = cx + dir * t * wingW
    const y = topY + t * t * wingH
    return `${x},${y}`
  }).join(' ')

  // Receiver tube (focal line at top-centre)
  const recvY = topY - 2

  return (
    <g>
      {strips}
      <polyline points={outerPts} fill="none" stroke="#1e2845" strokeWidth={2} />

      {/* Strut from outer bottom to mount */}
      <line x1={cx + dir * wingW * 0.95} y1={topY + wingH}
        x2={cx} y2={topY + wingH + 28}
        stroke="#1e2845" strokeWidth={2} />
      <line x1={cx + dir * wingW * 0.5} y1={topY + wingH * 0.6}
        x2={cx} y2={topY + wingH + 28}
        stroke="#1e2845" strokeWidth={1.5} />

      {/* Receiver tube glow */}
      <rect x={cx - 8} y={recvY - 3} width={16} height={6} rx={3}
        fill="#0e1020" />
      <rect x={cx - 8} y={recvY - 3} width={16} height={6} rx={3}
        fill={col} opacity={0.5 + heat * 0.5}
        style={{ filter: `drop-shadow(0 0 ${5 + heat * 10}px ${col})` }} />

      {/* Heat atmosphere */}
      {heat > 0.05 && (
        <ellipse cx={cx + dir * wingW * 0.4} cy={topY + wingH * 0.45}
          rx={wingW * 0.6} ry={wingH * 0.5}
          fill={col} opacity={heat * 0.07}
          style={{ filter: 'blur(14px)' }} />
      )}
    </g>
  )
}

function Tank({ x, y, w, h, temperature }) {
  const heat = temperature != null ? Math.max(0, Math.min(1, (temperature - 10) / 90)) : 0
  const col = tempColor(temperature, 10, 100)
  const lvl = h * 0.72
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10}
        fill="#0c0e18" stroke="#1e2440" strokeWidth={1} />
      <rect x={x + 2} y={y + h - lvl} width={w - 4} height={lvl - 2} rx={8}
        fill={col} opacity={0.15} />
      <line x1={x + 4} x2={x + w - 4} y1={y + h - lvl} y2={y + h - lvl}
        stroke={col} strokeWidth={1.5} opacity={0.5} strokeDasharray="5 3" />
      <rect x={x} y={y} width={w} height={h} rx={10}
        fill="none" stroke={col} strokeWidth={1.5} opacity={0.25 + heat * 0.55} />
    </g>
  )
}

export default function App() {
  const [data, setData] = useState({})
  const [lastUpdate, setLastUpdate] = useState(null)
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    const load = async () => {
      const d = await fetchLatestReadings()
      setData(d)
      setLastUpdate(new Date())
      const ts = d.temp_tank?.ts || d.temp_forward?.ts
      const age = ts ? (Date.now() - new Date(ts)) / 60000 : 999
      setIsLive(age < 15)
    }
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  const v = {}
  for (const [k, d] of Object.entries(data)) v[k] = d?.value

  const fwdColor = tempColor(v.temp_forward, 20, 120)
  const retColor = tempColor(v.temp_return,  10, 80)

  // Pipe routes — collectors meet at centre mount x:210, then to tank
  const fwdPipe = [[210, 358], [210, 415], [348, 415], [348, 335]]
  const retPipe = [[348, 380], [348, 450], [60,  450], [60,  358]]

  const timeStr = lastUpdate
    ? lastUpdate.toLocaleTimeString('sv-SE', { timeStyle: 'medium' })
    : '—:—:—'

  return (
    <div style={{
      minHeight: '100dvh', background: '#080910',
      fontFamily: "'Syne', sans-serif", color: '#ccd6f6',
      display: 'flex', flexDirection: 'column',
      maxWidth: 460, margin: '0 auto',
      paddingBottom: 'env(safe-area-inset-bottom)',
    }}>

      {/* Header */}
      <div style={{
        padding: '18px 20px 14px', borderBottom: '1px solid #12141f',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 23, fontWeight: 800, letterSpacing: '-0.02em', color: '#e6f1ff' }}>
            HELIXIS
          </div>
          <div style={{ fontSize: 10, color: '#2e3558', letterSpacing: '0.18em', marginTop: 1 }}>
            LC12 · LINEAR CONCENTRATOR
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
            <div style={{
              width: 7, height: 7, borderRadius: '50%',
              background: isLive ? '#00e5a0' : '#e55353',
              boxShadow: isLive ? '0 0 8px #00e5a0' : '0 0 8px #e55353',
            }} />
            <span style={{ fontSize: 10, color: isLive ? '#00e5a0' : '#e55353', letterSpacing: '0.12em' }}>
              {isLive ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
          <div style={{ fontSize: 10, color: '#2e3558', marginTop: 3, fontFamily: "'Space Mono', monospace" }}>
            {timeStr}
          </div>
        </div>
      </div>

      {/* System diagram */}
      <div style={{ padding: '10px 2px 4px' }}>
        <svg viewBox="0 0 420 500" width="100%" style={{ display: 'block', overflow: 'visible' }}>

          {/* Left collector — right wing curves left from centre */}
          <ParabolicCollector cx={210} topY={55} wingW={145} wingH={265}
            temperature={v.temp_left_coll} side="left" />

          {/* Right collector — left wing curves right from centre */}
          <ParabolicCollector cx={210} topY={55} wingW={145} wingH={265}
            temperature={v.temp_right_coll} side="right" />

          {/* Central mount pole */}
          <line x1={210} y1={320} x2={210} y2={358}
            stroke="#1e2440" strokeWidth={10} strokeLinecap="round" />
          <line x1={210} y1={320} x2={210} y2={358}
            stroke="#252a45" strokeWidth={5} strokeLinecap="round" />
          <rect x={192} y={353} width={36} height={10} rx={4}
            fill="#1a1f35" stroke="#252a45" strokeWidth={1} />

          {/* Storage tank */}
          <Tank x={316} y={140} w={78} h={210} temperature={v.temp_tank} />
          <text x={355} y={133} textAnchor="middle"
            fill="#2e3558" fontSize={9} letterSpacing="0.15em"
            fontFamily="'Space Mono', monospace">STORAGE</text>

          {/* Forward pipe */}
          <polyline points={fwdPipe.map(p => p.join(',')).join(' ')}
            fill="none" stroke={fwdColor} strokeWidth={6}
            strokeLinecap="round" strokeLinejoin="round" opacity={0.35} />
          <polyline points={fwdPipe.map(p => p.join(',')).join(' ')}
            fill="none" stroke={fwdColor} strokeWidth={2.5}
            strokeLinecap="round" strokeLinejoin="round"
            style={{ filter: `drop-shadow(0 0 5px ${fwdColor})` }} />

          {/* Return pipe */}
          <polyline points={retPipe.map(p => p.join(',')).join(' ')}
            fill="none" stroke={retColor} strokeWidth={6}
            strokeLinecap="round" strokeLinejoin="round" opacity={0.35} />
          <polyline points={retPipe.map(p => p.join(',')).join(' ')}
            fill="none" stroke={retColor} strokeWidth={2.5}
            strokeLinecap="round" strokeLinejoin="round"
            style={{ filter: `drop-shadow(0 0 5px ${retColor})` }} />

          {/* Tank stubs */}
          <line x1={348} y1={335} x2={348} y2={380}
            stroke="#12141f" strokeWidth={8} strokeLinecap="round" />

          {/* Flow particles */}
          {(v.flow ?? 0) > 0.005 && <>
            <FlowParticles path={fwdPipe} color={fwdColor} speed={(v.flow ?? 0.04) * 18} count={3} />
            <FlowParticles path={retPipe} color={retColor} speed={(v.flow ?? 0.04) * 18} count={3} />
          </>}

          {/* Sensor badges */}
          <Badge x={44}  y={90}  label="LEFT"   value={v.temp_left_coll}  color={tempColor(v.temp_left_coll,  20, 160)} align="right" />
          <Badge x={315} y={90}  label="RIGHT"  value={v.temp_right_coll} color={tempColor(v.temp_right_coll, 20, 160)} align="left" />
          <Badge x={316} y={255} label="TANK"   value={v.temp_tank}       color={tempColor(v.temp_tank, 10, 100)}       align="left" />
          <Badge x={210} y={415} label="FWD"    value={v.temp_forward}    color={fwdColor} align="right" />
          <Badge x={60}  y={450} label="RETURN" value={v.temp_return}     color={retColor} align="right" />

          {/* ΔT chip */}
          {v.temp_difference != null && (
            <g>
              <rect x={258} y={435} width={68} height={34} rx={6}
                fill="#0c0e18" stroke="#1a1f35" strokeWidth={1} />
              <text x={292} y={449} textAnchor="middle"
                fill="#2e3558" fontSize={9} letterSpacing="0.1em"
                fontFamily="'Space Mono', monospace">ΔT</text>
              <text x={292} y={463} textAnchor="middle"
                fill="#ccd6f6" fontSize={13} fontWeight="700"
                fontFamily="'Space Mono', monospace">{fmt(v.temp_difference, 1)}°</text>
            </g>
          )}
        </svg>
      </div>

      {/* Stats grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 1, background: '#12141f', borderTop: '1px solid #12141f', margin: '0 0 1px',
      }}>
        {[
          { label: 'POWER',    val: v.power,      dec: 2, unit: 'kW',   color: '#e87d4a' },
          { label: 'FLOW',     val: v.flow,       dec: 3, unit: 'm³/h', color: '#4a9ee8' },
          { label: 'IRRAD.',   val: v.irradiance, dec: 0, unit: 'W/m²', color: '#e8c84a' },
          { label: 'PRESSURE', val: v.pressure,   dec: 2, unit: 'bar',
            color: (v.pressure ?? 0) >= 5 ? '#e85353' : '#506080' },
        ].map(s => (
          <div key={s.label} style={{ background: '#080910', padding: '11px 6px', textAlign: 'center' }}>
            <div style={{ fontSize: 9, color: '#2e3558', letterSpacing: '0.12em', marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: s.color, lineHeight: 1,
              fontFamily: "'Space Mono', monospace" }}>
              {s.val != null ? s.val.toFixed(s.dec) : '—'}
            </div>
            <div style={{ fontSize: 9, color: '#2e3558', marginTop: 3 }}>{s.unit}</div>
          </div>
        ))}
      </div>

      {/* Energy + env */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: '#12141f' }}>
        {[
          { label: 'HEAT ENERGY', val: v.heat_energy, dec: 3, unit: 'kWh' },
          { label: 'WIND',        val: v.wind,        dec: 2, unit: 'm/s'  },
        ].map(s => (
          <div key={s.label} style={{
            background: '#080910', padding: '10px 14px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <span style={{ fontSize: 9, color: '#2e3558', letterSpacing: '0.12em' }}>{s.label}</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 15, fontWeight: 700, color: '#ccd6f6' }}>
              {s.val != null ? s.val.toFixed(s.dec) : '—'}
              <span style={{ fontSize: 9, color: '#2e3558', marginLeft: 4 }}>{s.unit}</span>
            </span>
          </div>
        ))}
      </div>

      <div style={{ padding: '10px 20px', fontSize: 9, color: '#181d30',
        letterSpacing: '0.1em', textAlign: 'center' }}>
        HELIXIS LC12 · 12.35 m² · 9.2 kW PEAK · 380 KG
      </div>
    </div>
  )
}
