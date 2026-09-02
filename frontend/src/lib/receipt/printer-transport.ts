"use client";

/**
 * Getting bytes to a thermal printer from a browser.
 *
 * Three transports, in descending order of directness:
 *   WebUSB      -- Chrome/Edge, printer plugged into the terminal
 *   Bluetooth   -- Chrome/Edge, portable printers
 *   PDF/print   -- everywhere, including Safari and Firefox
 *
 * WebUSB and Web Bluetooth both require a secure context (HTTPS or
 * localhost) and a user gesture to choose the device -- a page cannot silently
 * enumerate hardware. Neither is supported in Safari or Firefox at all, which
 * is why the print path is not a fallback so much as a first-class option.
 */

export type TransportKind = "usb" | "bluetooth" | "pdf";

export interface PrinterTransport {
  kind: TransportKind;
  label: string;
  write(data: Uint8Array): Promise<void>;
  disconnect(): Promise<void>;
}

export function isWebUsbSupported(): boolean {
  return typeof navigator !== "undefined" && "usb" in navigator;
}

export function isWebBluetoothSupported(): boolean {
  return typeof navigator !== "undefined" && "bluetooth" in navigator;
}

export function isSecureContextOk(): boolean {
  return typeof window !== "undefined" && window.isSecureContext;
}

/** USB printer class. Filtering on it keeps the chooser to actual printers. */
const PRINTER_CLASS = 0x07;

export async function connectUsbPrinter(): Promise<PrinterTransport> {
  if (!isWebUsbSupported()) {
    throw new Error("This browser does not support WebUSB. Use Chrome or Edge.");
  }
  if (!isSecureContextOk()) {
    throw new Error("WebUSB needs HTTPS (or localhost).");
  }

  const device = await navigator.usb.requestDevice({
    filters: [{ classCode: PRINTER_CLASS }],
  });

  await device.open();
  if (device.configuration === null) {
    await device.selectConfiguration(1);
  }

  // Find the interface exposing a bulk OUT endpoint -- that is where the
  // byte stream goes. Vendor-specific interfaces vary, so this is discovered
  // rather than hardcoded.
  let interfaceNumber: number | null = null;
  let endpointNumber: number | null = null;

  for (const iface of device.configuration?.interfaces ?? []) {
    for (const alternate of iface.alternates) {
      if (
        alternate.interfaceClass !== PRINTER_CLASS &&
        alternate.interfaceClass !== 0xff
      ) {
        continue;
      }
      const endpoint = alternate.endpoints.find(
        (e) => e.direction === "out" && e.type === "bulk",
      );
      if (endpoint) {
        interfaceNumber = iface.interfaceNumber;
        endpointNumber = endpoint.endpointNumber;
        break;
      }
    }
    if (interfaceNumber !== null) break;
  }

  if (interfaceNumber === null || endpointNumber === null) {
    await device.close();
    throw new Error("No printable interface found on that device.");
  }

  await device.claimInterface(interfaceNumber);

  return {
    kind: "usb",
    label: device.productName || "USB printer",
    async write(data) {
      await device.transferOut(endpointNumber, data as BufferSource);
    },
    async disconnect() {
      try {
        await device.releaseInterface(interfaceNumber);
        await device.close();
      } catch {
        // The device may already be gone; nothing useful to do about it.
      }
    },
  };
}

// The de-facto standard serial-over-BLE service used by portable ESC/POS
// printers. Vendors differ, so the chooser also accepts any device by name.
const BLE_PRINTER_SERVICES = [
  0x18f0,
  "000018f0-0000-1000-8000-00805f9b34fb",
  "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
];

export async function connectBluetoothPrinter(): Promise<PrinterTransport> {
  if (!isWebBluetoothSupported()) {
    throw new Error("This browser does not support Web Bluetooth.");
  }

  const device = await navigator.bluetooth.requestDevice({
    filters: BLE_PRINTER_SERVICES.map((service) => ({ services: [service] })),
    optionalServices: BLE_PRINTER_SERVICES,
  });

  const server = await device.gatt?.connect();
  if (!server) throw new Error("Could not connect to the printer.");

  let characteristic: BluetoothRemoteGATTCharacteristic | null = null;
  for (const service of await server.getPrimaryServices()) {
    for (const candidate of await service.getCharacteristics()) {
      if (candidate.properties.write || candidate.properties.writeWithoutResponse) {
        characteristic = candidate;
        break;
      }
    }
    if (characteristic) break;
  }
  if (!characteristic) throw new Error("Printer exposes no writable channel.");

  return {
    kind: "bluetooth",
    label: device.name || "Bluetooth printer",
    async write(data) {
      // BLE caps a single write at 20 bytes on many stacks; a receipt is
      // kilobytes, so it is chunked. Writes are awaited in order -- firing
      // them in parallel interleaves the bytes and prints garbage.
      const CHUNK = 20;
      for (let offset = 0; offset < data.length; offset += CHUNK) {
        await characteristic.writeValueWithoutResponse(
          data.slice(offset, offset + CHUNK) as BufferSource,
        );
      }
    },
    async disconnect() {
      device.gatt?.disconnect();
    },
  };
}
