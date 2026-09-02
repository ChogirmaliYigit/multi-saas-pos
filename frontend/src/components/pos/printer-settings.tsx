"use client";

import { Bluetooth, Loader2, Printer, Usb, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  connectBluetoothPrinter,
  connectUsbPrinter,
  isSecureContextOk,
  isWebBluetoothSupported,
  isWebUsbSupported,
} from "@/lib/receipt/printer-transport";
import { usePrinterStore } from "@/lib/stores/printer-store";
import { cn } from "@/lib/utils";

export function PrinterSettings({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const store = usePrinterStore();
  const [connecting, setConnecting] = useState<"usb" | "bluetooth" | null>(null);

  const usbAvailable = isWebUsbSupported() && isSecureContextOk();
  const bleAvailable = isWebBluetoothSupported() && isSecureContextOk();

  async function connect(kind: "usb" | "bluetooth") {
    setConnecting(kind);
    try {
      const transport =
        kind === "usb"
          ? await connectUsbPrinter()
          : await connectBluetoothPrinter();
      store.setTransport(transport);
      store.setPreferred(kind);
      toast.success(`Connected to ${transport.label}`);
    } catch (error) {
      // A cancelled device chooser is a NotFoundError, not a failure worth
      // shouting about.
      const message = error instanceof Error ? error.message : "Could not connect.";
      if (!/cancell?ed|No device selected/i.test(message)) toast.error(message);
    } finally {
      setConnecting(null);
    }
  }

  async function disconnect() {
    await store.transport?.disconnect();
    store.setTransport(null);
    store.setPreferred("pdf");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Receipt printer</DialogTitle>
          <DialogDescription>
            Connect a thermal printer directly, or print through the browser.
          </DialogDescription>
        </DialogHeader>

        {store.transport ? (
          <div className="border-primary/40 bg-primary/5 flex items-center gap-3 rounded-lg border p-3">
            <Printer className="text-primary size-5" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {store.transport.label}
              </p>
              <p className="text-muted-foreground text-xs">
                Connected over{" "}
                {store.transport.kind === "usb" ? "USB" : "Bluetooth"}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={disconnect}
              aria-label="Disconnect"
            >
              <X className="size-4" />
            </Button>
          </div>
        ) : (
          <div className="grid gap-2">
            <ConnectButton
              icon={Usb}
              label="Connect USB printer"
              hint={
                !isWebUsbSupported()
                  ? "Needs Chrome or Edge"
                  : !isSecureContextOk()
                    ? "Needs HTTPS"
                    : "Epson-compatible ESC/POS"
              }
              disabled={!usbAvailable}
              busy={connecting === "usb"}
              onClick={() => connect("usb")}
            />
            <ConnectButton
              icon={Bluetooth}
              label="Connect Bluetooth printer"
              hint={
                !isWebBluetoothSupported()
                  ? "Needs Chrome or Edge"
                  : !isSecureContextOk()
                    ? "Needs HTTPS"
                    : "Portable ESC/POS"
              }
              disabled={!bleAvailable}
              busy={connecting === "bluetooth"}
              onClick={() => connect("bluetooth")}
            />
          </div>
        )}

        {!usbAvailable && !bleAvailable && (
          <p className="text-muted-foreground text-xs">
            Direct printing needs Chrome or Edge over HTTPS. Receipts will print
            through the browser dialog instead, which also drives a thermal printer
            through its normal driver.
          </p>
        )}

        <Separator />

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Paper width</Label>
            <div className="grid grid-cols-2 gap-2">
              {([58, 80] as const).map((mm) => (
                <button
                  key={mm}
                  type="button"
                  onClick={() => store.setPaper(mm)}
                  className={cn(
                    "touch-target rounded-lg border p-2.5 text-sm transition-colors",
                    store.paperMm === mm
                      ? "border-primary bg-primary/10 font-medium"
                      : "hover:bg-accent",
                  )}
                >
                  {mm}mm
                  <span className="text-muted-foreground block text-xs">
                    {mm === 58 ? "32 columns" : "48 columns"}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <ToggleRow
            id="auto-print"
            label="Print automatically"
            hint={
              store.transport
                ? "Print as soon as a sale completes."
                : "Applies once a printer is connected. Without one, printing goes through the browser dialog, so it waits for you to press Print."
            }
            checked={store.autoPrint}
            onChange={store.setAutoPrint}
          />
          <ToggleRow
            id="open-drawer"
            label="Open drawer on cash"
            hint="Sends the drawer-kick pulse through the printer."
            checked={store.openDrawerOnCash}
            onChange={store.setOpenDrawerOnCash}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ConnectButton({
  icon: Icon,
  label,
  hint,
  disabled,
  busy,
  onClick,
}: {
  icon: typeof Usb;
  label: string;
  hint: string;
  disabled: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={cn(
        "flex items-center gap-3 rounded-lg border p-3 text-left transition-colors",
        "hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent",
      )}
    >
      {busy ? (
        <Loader2 className="size-5 animate-spin" />
      ) : (
        <Icon className="text-muted-foreground size-5" />
      )}
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        <span className="text-muted-foreground block text-xs">{hint}</span>
      </span>
    </button>
  );
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
