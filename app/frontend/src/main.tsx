import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import './index.css'
import Queue from './pages/Queue'
import Detail from './pages/Detail'
import Outbound from './pages/Outbound'

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="topbar">
        <div className="logo"><span className="dot" /> Order Intake Review</div>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>Review Queue</NavLink>
          <NavLink to="/outbound" className={({ isActive }) => (isActive ? 'active' : '')}>SAP Outbound</NavLink>
        </nav>
        <div className="spacer" />
        <div className="user">Human-in-the-loop PO review</div>
      </div>
      {children}
    </>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Queue />} />
          <Route path="/orders/:id" element={<Detail />} />
          <Route path="/outbound" element={<Outbound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </React.StrictMode>
)
