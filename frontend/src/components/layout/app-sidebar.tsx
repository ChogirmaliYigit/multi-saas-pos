"use client";

import { motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen, Store } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { NavSection } from "@/lib/navigation";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useUiStore } from "@/lib/stores/ui-store";

interface AppSidebarProps {
  sections: NavSection[];
  /** Rendered under the nav, e.g. the "Open POS terminal" call to action. */
  footer?: React.ReactNode;
  /**
   * Overrides the shop name/role shown in the header. The platform shell has
   * no tenant, so without this it fell back to "Shop admin" for an operator
   * who runs the whole platform.
   */
  title?: string;
  subtitle?: string;
}

export function AppSidebar({ sections, footer, title, subtitle }: AppSidebarProps) {
  const pathname = usePathname();
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  const permissions = useAuthStore((s) => s.permissions);
  const tenantSlug = useAuthStore((s) => s.tenantSlug);

  return (
    <motion.aside
      animate={{ width: collapsed ? 68 : 256 }}
      transition={{ type: "spring", stiffness: 400, damping: 34 }}
      className="bg-sidebar text-sidebar-foreground hidden shrink-0 border-r md:flex md:flex-col"
    >
      <div className="flex h-14 items-center gap-2 border-b px-3">
        <div className="bg-primary text-primary-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
          <Store className="size-4.5" />
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">
              {title ?? tenantSlug ?? "POS"}
            </p>
            <p className="text-muted-foreground truncate text-xs">
              {subtitle ?? "Shop admin"}
            </p>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1">
        <nav className="flex flex-col gap-4 p-2">
          {sections.map((section) => {
            const visible = section.items.filter(
              (item) => !item.permission || permissions.has(item.permission),
            );
            if (visible.length === 0) return null;

            return (
              <div key={section.label} className="flex flex-col gap-0.5">
                {!collapsed && (
                  <p className="text-muted-foreground px-3 pt-1 pb-1 text-xs font-medium tracking-wide uppercase">
                    {section.label}
                  </p>
                )}
                {visible.map((item) => {
                  const active = item.exact
                    ? pathname === item.href
                    : pathname.startsWith(item.href);
                  const link = (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                          : "text-muted-foreground",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      {active && (
                        // Shared layoutId slides the indicator between items
                        // instead of cross-fading, which reads as one object
                        // moving rather than two appearing.
                        <motion.span
                          layoutId="sidebar-active"
                          className="bg-primary absolute inset-y-1 left-0 w-0.5 rounded-full"
                          transition={{
                            type: "spring",
                            stiffness: 500,
                            damping: 38,
                          }}
                        />
                      )}
                      <item.icon className="size-4.5 shrink-0" />
                      {!collapsed && <span className="truncate">{item.title}</span>}
                    </Link>
                  );

                  return collapsed ? (
                    <Tooltip key={item.href}>
                      <TooltipTrigger asChild>{link}</TooltipTrigger>
                      <TooltipContent side="right">{item.title}</TooltipContent>
                    </Tooltip>
                  ) : (
                    link
                  );
                })}
              </div>
            );
          })}
        </nav>
      </ScrollArea>

      {footer && <div className="border-t p-2">{footer}</div>}

      <div className="border-t p-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={toggle}
          className="text-muted-foreground w-full justify-center"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" />
          ) : (
            <>
              <PanelLeftClose className="size-4" /> Collapse
            </>
          )}
        </Button>
      </div>
    </motion.aside>
  );
}
