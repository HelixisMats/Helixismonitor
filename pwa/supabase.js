import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(url, key)

export async function fetchLatestReadings() {
  // Get the latest value per sensor from the last 10 minutes
  const since = new Date(Date.now() - 10 * 60 * 1000).toISOString()
  const { data, error } = await supabase
    .from('sensor_readings')
    .select('sensor, value, created_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })

  if (error || !data) return {}

  // Keep only the most recent value per sensor
  const latest = {}
  for (const row of data) {
    if (!(row.sensor in latest)) {
      latest[row.sensor] = { value: row.value, ts: row.created_at }
    }
  }
  return latest
}
