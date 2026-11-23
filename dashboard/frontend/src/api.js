const BASE = '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${path} failed (${res.status})`)
  }
  return res.json()
}

async function getOrNull(path) {
  const res = await fetch(`${BASE}${path}`)
  if (res.status === 404) return null
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${path} failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  rankings: () => get('/rankings'),
  backtest: () => get('/backtest'),
  backtestTimeline: (company) => getOrNull(`/backtest/timeline/${encodeURIComponent(company)}`),
  optimalPortfolio: () => get('/optimal-portfolio'),
  sensitivity: () => get('/sensitivity'),
  robustPortfolio: () => get('/robust-portfolio'),
  weightCalibration: () => get('/weight-calibration'),
  keyFindings: () => get('/key-findings'),
  explain: (company) => getOrNull(`/explain/${encodeURIComponent(company)}`),
  explainAtDate: (company, date) => getOrNull(`/explain/${encodeURIComponent(company)}/${encodeURIComponent(date)}`),
}
