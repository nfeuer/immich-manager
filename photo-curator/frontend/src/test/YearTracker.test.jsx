import { render, screen, fireEvent } from '@testing-library/react'
import YearTracker from '../components/YearTracker'

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

describe('YearTracker', () => {
  it('renders 12 month pills', () => {
    const progress = Object.fromEntries(Array.from({length:12},(_,i)=>[i+1, false]))
    render(<YearTracker year={2024} progress={progress} currentMonth={3} onSelect={()=>{}} />)
    MONTHS.forEach(m => expect(screen.getByText(m)).toBeInTheDocument())
  })

  it('marks curated months as green', () => {
    const progress = { ...Object.fromEntries(Array.from({length:12},(_,i)=>[i+1,false])), 1: true, 3: true }
    render(<YearTracker year={2024} progress={progress} currentMonth={3} onSelect={()=>{}} />)
    // Curated pills have data-curated="true"
    const curated = screen.getAllByTestId('month-pill').filter(el => el.dataset.curated === 'true')
    expect(curated).toHaveLength(2)
  })

  it('calls onSelect with month number when a pill is clicked', () => {
    const onSelect = vi.fn()
    const progress = Object.fromEntries(Array.from({length:12},(_,i)=>[i+1, false]))
    render(<YearTracker year={2024} progress={progress} currentMonth={1} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Mar'))
    expect(onSelect).toHaveBeenCalledWith(3)
  })
})
