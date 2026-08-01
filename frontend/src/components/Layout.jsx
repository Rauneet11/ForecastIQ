import React, { useState, useCallback } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import {
  FiGrid, FiUpload, FiTrendingUp, FiBarChart2, FiZap,
  FiClock, FiFileText, FiUser, FiLogOut,
  FiSun, FiMoon, FiMenu, FiX, FiShield,
  FiChevronRight, FiBell
} from 'react-icons/fi'
import { BsGraphUpArrow } from 'react-icons/bs'
import toast from 'react-hot-toast'

const NAV_ITEMS = [
  { to: '/dashboard',       label: 'Dashboard',       icon: FiGrid,         roles: ['admin','manager','analyst'] },
  { to: '/upload',          label: 'Upload Dataset',  icon: FiUpload,       roles: ['admin','manager'] },
  { to: '/predictions',     label: 'Predictions',     icon: FiTrendingUp,   roles: ['admin','manager','analyst'] },
  { to: '/forecast',        label: 'Forecast Charts', icon: FiBarChart2,    roles: ['admin','manager','analyst'] },
  { to: '/simulator',       label: 'Scenario Sim',    icon: FiZap,          roles: ['admin','analyst'] },
  { to: '/recommendations', label: 'AI Insights',     icon: BsGraphUpArrow, roles: ['admin','manager','analyst'] },
  { to: '/history',         label: 'History',         icon: FiClock,        roles: ['admin','manager','analyst'] },
  { to: '/reports',         label: 'Reports',         icon: FiFileText,     roles: ['admin','manager','analyst'] },
  { to: '/admin-panel',     label: 'Admin Panel',     icon: FiShield,       roles: ['admin'] },
]

/* Maps route path → human-friendly page title */
const PAGE_TITLES = {
  '/dashboard':       'Dashboard',
  '/upload':          'Upload Dataset',
  '/predictions':     'Predictions',
  '/forecast':        'Forecast Charts',
  '/simulator':       'Scenario Simulator',
  '/recommendations': 'AI Insights',
  '/history':         'History',
  '/reports':         'Reports',
  '/profile':         'My Profile',
  '/admin-panel':     'Admin Panel',
}

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  // Desktop: collapsed (icon-only) vs expanded
  const [sidebarOpen, setSidebarOpen] = useState(true)
  // Mobile: drawer open/closed
  const [mobileSidebar, setMobileSidebar] = useState(false)

  const handleLogout = useCallback(async () => {
    await logout()
    toast.success('Logged out successfully')
    navigate('/login')
  }, [logout, navigate])

  const closeMobile = useCallback(() => setMobileSidebar(false), [])

  const visibleNav = NAV_ITEMS.filter(item => item.roles.includes(user?.role))
  const pageTitle = PAGE_TITLES[location.pathname] ?? 'SalesCast AI'

  /* ── Shared sidebar nav content ───────────────────────────────────── */
  const SidebarNav = ({ collapsed = false, onLinkClick }) => (
    <div className="flex flex-col h-full">

      {/* Logo header */}
      <div className={`flex items-center border-b border-white/10 ${collapsed ? 'justify-center px-0 py-5' : 'gap-3 px-5 py-5'}`}>
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center shadow-lg flex-shrink-0">
          <BsGraphUpArrow className="text-white text-lg" />
        </div>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              key="logo-text"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden whitespace-nowrap"
            >
              <p className="font-bold text-white text-sm leading-tight">SalesCast AI</p>
              <p className="text-white/50 text-xs">Revenue Forecasting</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation links */}
      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {visibleNav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onLinkClick}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center rounded-xl transition-all duration-200 text-sm font-medium group relative
               ${collapsed ? 'justify-center px-0 py-3 mx-1' : 'gap-3 px-3 py-2.5'}
               ${isActive
                 ? 'bg-white/15 text-white shadow-sm'
                 : 'text-white/60 hover:bg-white/10 hover:text-white'
               }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={`text-lg flex-shrink-0 ${isActive ? 'text-white' : 'text-white/60 group-hover:text-white'}`} />
                <AnimatePresence initial={false}>
                  {!collapsed && (
                    <motion.span
                      key="nav-label"
                      initial={{ opacity: 0, width: 0 }}
                      animate={{ opacity: 1, width: 'auto' }}
                      exit={{ opacity: 0, width: 0 }}
                      transition={{ duration: 0.2 }}
                      className="truncate overflow-hidden whitespace-nowrap flex-1"
                    >
                      {label}
                    </motion.span>
                  )}
                </AnimatePresence>
                {isActive && !collapsed && (
                  <FiChevronRight className="ml-auto text-white/50 text-xs flex-shrink-0" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User profile & logout */}
      <div className={`border-t border-white/10 space-y-0.5 ${collapsed ? 'px-2 py-3' : 'p-3'}`}>
        <NavLink
          to="/profile"
          onClick={onLinkClick}
          title={collapsed ? user?.username : undefined}
          className={({ isActive }) =>
            `flex items-center rounded-xl text-sm font-medium transition-all duration-200
             ${collapsed ? 'justify-center px-0 py-3 mx-1' : 'gap-3 px-3 py-2.5'}
             ${isActive ? 'bg-white/15 text-white' : 'text-white/60 hover:bg-white/10 hover:text-white'}`
          }
        >
          {user?.profile_photo
            ? <img src={user.profile_photo} className="w-7 h-7 rounded-full object-cover border border-white/20 flex-shrink-0" alt="avatar" />
            : <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                {user?.username?.[0]?.toUpperCase()}
              </div>
          }
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div
                key="user-info"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden whitespace-nowrap"
              >
                <p className="text-white text-sm font-medium truncate">{user?.username}</p>
                <p className="text-white/40 text-xs capitalize">{user?.role}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </NavLink>

        <button
          onClick={handleLogout}
          title={collapsed ? 'Logout' : undefined}
          className={`w-full flex items-center rounded-xl text-sm font-medium text-red-300 hover:bg-red-500/20 hover:text-red-200 transition-all duration-200
            ${collapsed ? 'justify-center px-0 py-3 mx-auto' : 'gap-3 px-3 py-2.5'}`}
          style={collapsed ? { width: 'calc(100% - 8px)', marginLeft: 4 } : {}}
        >
          <FiLogOut className="text-lg flex-shrink-0" />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span
                key="logout-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden whitespace-nowrap"
              >
                Logout
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </div>
  )

  const sidebarBg = 'linear-gradient(180deg, #0f172a 0%, #1e3a8a 50%, #0f172a 100%)'

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">

      {/* ── Desktop Sidebar ─────────────────────────────────────────── */}
      <motion.aside
        animate={{ width: sidebarOpen ? 240 : 68 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="hidden md:flex flex-col flex-shrink-0 overflow-hidden z-10 shadow-2xl"
        style={{ background: sidebarBg, minWidth: sidebarOpen ? 240 : 68 }}
      >
        <SidebarNav collapsed={!sidebarOpen} />
      </motion.aside>

      {/* ── Mobile Sidebar Overlay ───────────────────────────────────── */}
      <AnimatePresence>
        {mobileSidebar && (
          <>
            {/* Backdrop */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeMobile}
              className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            />
            {/* Drawer */}
            <motion.aside
              key="drawer"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="md:hidden fixed left-0 top-0 bottom-0 w-64 z-50 shadow-2xl flex flex-col"
              style={{ background: sidebarBg }}
            >
              {/* Mobile close button */}
              <button
                onClick={closeMobile}
                className="absolute top-4 right-4 w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors z-10"
              >
                <FiX className="text-white text-lg" />
              </button>
              <SidebarNav collapsed={false} onLinkClick={closeMobile} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ── Main Content ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Top bar */}
        <header className="h-16 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-700/50 flex items-center px-4 md:px-6 gap-3 flex-shrink-0 z-10 shadow-sm">

          {/* ☰ Hamburger — visible on ALL screen sizes */}
          <button
            id="sidebar-toggle-btn"
            onClick={() => {
              if (window.innerWidth >= 768) {
                setSidebarOpen(s => !s)   // desktop: collapse/expand
              } else {
                setMobileSidebar(s => !s) // mobile: open drawer
              }
            }}
            className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors flex-shrink-0"
            title="Toggle sidebar"
          >
            <FiMenu className="text-xl" />
          </button>

          {/* Page title / breadcrumb */}
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-slate-800 dark:text-slate-100 truncate">
              {pageTitle}
            </h1>
          </div>

          {/* Right-side actions */}
          <div className="flex items-center gap-1.5">
            {/* Dark mode toggle */}
            <button
              onClick={toggle}
              className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-all"
              title="Toggle dark mode"
            >
              {dark ? <FiSun className="text-lg" /> : <FiMoon className="text-lg" />}
            </button>

            {/* Notifications */}
            <button className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-all relative">
              <FiBell className="text-lg" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>

            {/* Avatar / profile link */}
            <NavLink
              to="/profile"
              className="flex items-center gap-2 pl-2 border-l border-slate-200 dark:border-slate-700 ml-1"
            >
              {user?.profile_photo
                ? <img src={user.profile_photo} className="w-8 h-8 rounded-full object-cover" alt="" />
                : <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-sm font-bold">
                    {user?.username?.[0]?.toUpperCase()}
                  </div>
              }
              <div className="hidden sm:block">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 leading-tight">
                  {user?.first_name || user?.username}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400 capitalize">{user?.role}</p>
              </div>
            </NavLink>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            {children}
          </motion.div>
        </main>
      </div>
    </div>
  )
}
