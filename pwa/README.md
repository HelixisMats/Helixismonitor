# Helixis LC Monitor — PWA

## Setup

1. Open `config.js` and replace `YOUR_ANON_KEY_HERE` with your Supabase **anon** key
   (Settings → API → Project API keys → anon/public)

2. Deploy to Vercel:
   - Go to vercel.com → New Project → Import from GitHub
   - Select HelixisMats/Helixismonitor
   - Set **Root directory** to `pwa`
   - Deploy

## Install on phone

**iPhone:** Open in Safari → Share → Add to Home Screen
**Android:** Open in Chrome → Menu → Add to Home Screen

## Files

- `index.html` — the entire app (React + charts + gauges)
- `config.js` — Supabase credentials (do NOT commit real keys)
- `manifest.json` — PWA metadata for home screen install
