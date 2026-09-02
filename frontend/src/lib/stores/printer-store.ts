"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type {
  PrinterTransport,
  TransportKind,
} from "@/lib/receipt/printer-transport";

interface PrinterState {
  /** Preference is persisted; the live connection is not (and cannot be). */
  preferred: TransportKind;
  paperMm: 58 | 80;
  autoPrint: boolean;
  openDrawerOnCash: boolean;

  transport: PrinterTransport | null;
  connecting: boolean;

  setPreferred: (kind: TransportKind) => void;
  setPaper: (mm: 58 | 80) => void;
  setAutoPrint: (value: boolean) => void;
  setOpenDrawerOnCash: (value: boolean) => void;
  setTransport: (transport: PrinterTransport | null) => void;
  setConnecting: (value: boolean) => void;
}

/**
 * A WebUSB/Bluetooth handle cannot be persisted -- permission is granted per
 * device per session and the object is not serialisable. So settings persist
 * and the connection is re-established by a click after each reload, which is
 * also what the permission model requires.
 */
export const usePrinterStore = create<PrinterState>()(
  persist(
    (set) => ({
      preferred: "pdf",
      paperMm: 80,
      autoPrint: true,
      openDrawerOnCash: true,
      transport: null,
      connecting: false,

      setPreferred: (preferred) => set({ preferred }),
      setPaper: (paperMm) => set({ paperMm }),
      setAutoPrint: (autoPrint) => set({ autoPrint }),
      setOpenDrawerOnCash: (openDrawerOnCash) => set({ openDrawerOnCash }),
      setTransport: (transport) => set({ transport }),
      setConnecting: (connecting) => set({ connecting }),
    }),
    {
      name: "pos-printer",
      partialize: (state) => ({
        preferred: state.preferred,
        paperMm: state.paperMm,
        autoPrint: state.autoPrint,
        openDrawerOnCash: state.openDrawerOnCash,
      }),
    },
  ),
);
