import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)

export async function fetchLatestReadings() {
  const since = new Date(Date.now() - 10 * 60 * 1000).toISOString()
  const { data, error } = await supabase
    .from('sensor_readings')
    .select('sensor,value,created_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
  if (error || !data) return {}
  const latest = {}
  for (const row of data) {
    if (!(row.sensor in latest))
      latest[row.sensor] = { value: row.value, ts: row.created_at }
  }
  return latest
}

export async function fetchTodayPower() {
  // Local midnight (phone is on Swedish time); toISOString() converts to UTC
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)

  const all = []
  let offset = 0
  while (true) {
    const { data } = await supabase
      .from('sensor_readings')
      .select('value,created_at')
      .eq('sensor', 'power')
      .gte('created_at', midnight.toISOString())
      .order('created_at', { ascending: true })
      .range(offset, offset + 999)
    if (!data?.length) break
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
}
