import { useState } from 'react'
import Header from './components/Header'
import KeyFindingsBanner from './components/KeyFindingsBanner'
import RankingsPanel from './components/RankingsPanel'
import BacktestPanel from './components/BacktestPanel'
import ReplayPanel from './components/ReplayPanel'
import OptimalPortfolioPanel from './components/OptimalPortfolioPanel'
import SensitivityPanel from './components/SensitivityPanel'
import RobustPortfolioPanel from './components/RobustPortfolioPanel'

const PANELS = {
  rankings: RankingsPanel,
  backtest: BacktestPanel,
  replay: ReplayPanel,
  portfolio: OptimalPortfolioPanel,
  sensitivity: SensitivityPanel,
  robust: RobustPortfolioPanel,
}

export default function App() {
  const [activeTab, setActiveTab] = useState('rankings')
  const ActivePanel = PANELS[activeTab]

  return (
    <div className="min-h-screen bg-[var(--surface-0)]">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="mx-auto max-w-7xl px-4 sm:px-6 py-6 flex flex-col gap-6">
        <KeyFindingsBanner />
        <ActivePanel />
      </main>
      <footer className="mx-auto max-w-7xl px-4 sm:px-6 pb-8 pt-2 text-xs text-[var(--text-muted)]">
        Quarry — LBO/PE target screening and capital allocation engine. Data from yfinance and SEC EDGAR; for research purposes, not investment advice.
      </footer>
    </div>
  )
}
