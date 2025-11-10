import React from "react";
import { NavLink } from "react-router-dom";
import s from "./Header.module.css";

export default function Header() {
  return (
    <header className={s.header}>
      <div className={s.inner}>
        <div className={s.brand}>
          <span className={s.logoDot} aria-hidden />
          <span className={s.brandText}>Danske Bank</span>
          <span className={s.badge}>Demo</span>
        </div>

        <nav className={s.nav} aria-label="Primary">
          <NavLink to="/" end className={({isActive}) => isActive ? `${s.link} ${s.active}` : s.link}>
            Home
          </NavLink>
          <NavLink to="/clients" className={({isActive}) => isActive ? `${s.link} ${s.active}` : s.link}>
            Clients
          </NavLink>
          <NavLink to="/verify" className={({isActive}) => isActive ? `${s.link} ${s.active}` : s.link}>
            Verify
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
