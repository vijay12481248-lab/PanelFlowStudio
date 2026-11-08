import React from "react";
import { NavLink, Outlet } from "react-router";
import { PageHeader } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";
import { SETTINGS_SECTIONS } from "./sections";

/** One Settings area: a section list and the section beside it (stacked on a narrow window). */
export const SettingsLayout: React.FC = () => (
  <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-6 p-6 md:p-8">
    <PageHeader title="Settings" />
    <div className="flex flex-col gap-6 min-[900px]:flex-row">
      <nav aria-label="Settings sections" className="flex shrink-0 gap-1 overflow-x-auto min-[900px]:w-56 min-[900px]:flex-col">
        {SETTINGS_SECTIONS.map((section) => (
          <NavLink
            key={section.id}
            to={paths.settings(section.id)}
            className={({ isActive }) =>
              `grid rounded-ctl border px-3 py-2 transition-colors duration-(--duration-fast) focus-visible:outline-2 focus-visible:outline-info ${
                isActive ? "border-accent/40 bg-accent-soft text-fg" : "border-transparent text-fg-dim hover:bg-glass hover:text-fg"
              }`
            }
          >
            <span data-section-label className="text-sm font-medium">{section.label}</span>
            <span className="hidden text-xs text-fg-faint min-[900px]:block">{section.description}</span>
          </NavLink>
        ))}
      </nav>
      <div className="min-w-0 flex-1"><Outlet /></div>
    </div>
  </div>
);
