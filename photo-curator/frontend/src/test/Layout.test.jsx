import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import BottomTabBar from '../components/BottomTabBar'

const NAV_LABELS = ['AI Album Curator', 'Import', 'Duplicates', 'Events & Trips', 'Analytics', 'Preferences']

describe('Sidebar', () => {
  it('renders all nav items', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={0} />
      </MemoryRouter>
    )
    NAV_LABELS.forEach(label => {
      expect(screen.getByText(label)).toBeInTheDocument()
    })
  })

  it('shows badge when uncuratedCount > 0', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={5} />
      </MemoryRouter>
    )
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('hides badge when uncuratedCount is 0', () => {
    render(
      <MemoryRouter>
        <Sidebar uncuratedCount={0} />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('curator-badge')).not.toBeInTheDocument()
  })
})

describe('BottomTabBar', () => {
  it('renders 6 tab icons', () => {
    render(
      <MemoryRouter>
        <BottomTabBar />
      </MemoryRouter>
    )
    // 6 nav links
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(6)
  })
})
